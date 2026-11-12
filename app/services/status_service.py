import json
from app.extensions import db
from app.models.base import BaseModel
from app.models.settings import AuditLog


class StatusServiceError(Exception):
    """Raised when an entity status cannot be changed."""


class StatusService:
    @staticmethod
    def toggle(record, user_id, entity_name=None):
        if not isinstance(record, BaseModel):
            raise StatusServiceError('This record does not support active status.')
        if record.is_deleted:
            raise StatusServiceError('Deleted records cannot be toggled.')

        old_status = record.status
        record.status = 'deactive' if old_status == 'active' else 'active'
        if hasattr(record, 'is_active'):
            record.is_active = record.status == 'active'
        if hasattr(record, 'is_published'):
            record.is_published = record.status == 'active'
        record.updated_by = user_id
        try:
            db.session.add(AuditLog(
                user_id=user_id,
                action='DEACTIVATE' if record.status == 'deactive' else 'ACTIVATE',
                target_entity=entity_name or type(record).__name__,
                target_id=record.id,
                details_json=json.dumps({
                    'old_status': old_status,
                    'new_status': record.status
                }),
                created_by=user_id
            ))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            raise StatusServiceError(f'Failed to update status: {exc}') from exc
        return record
