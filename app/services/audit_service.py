import json
from flask import request, has_request_context
from app.extensions import db
from app.models.settings import AuditLog


class AuditService:
    @staticmethod
    def log(action, target_entity, target_id=None, details=None, user_id=None, ip_address=None):
        """
        Records an audit log entry for security and administrative visibility.
        """
        if ip_address is None and has_request_context():
            ip_address = request.remote_addr

        if user_id is None and has_request_context():
            try:
                from flask_login import current_user
                if current_user and current_user.is_authenticated:
                    user_id = current_user.id
            except Exception:
                pass

        details_str = None
        if details is not None:
            if isinstance(details, (dict, list)):
                details_str = json.dumps(details, default=str)
            else:
                details_str = str(details)

        try:
            audit = AuditLog(
                user_id=user_id,
                action=action.upper(),
                target_entity=target_entity,
                target_id=target_id,
                details_json=details_str,
                ip_address=ip_address,
                created_by=user_id
            )
            db.session.add(audit)
            db.session.commit()
            return audit
        except Exception:
            db.session.rollback()
            return None
