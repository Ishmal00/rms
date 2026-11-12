from datetime import datetime
from flask import has_request_context
from sqlalchemy import event, orm
from sqlalchemy.orm import declared_attr
from app.extensions import db


class BaseModel(db.Model):
    """
    Abstract BaseModel inherited by all models.
    Provides standard audit columns, soft-delete functionality,
    and automatic user tracking.
    """
    __abstract__ = True

    # Primary key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Status & Soft Delete
    status = db.Column(db.String(20), default='active', nullable=False, index=True)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)

    # Audit timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    deleted_at = db.Column(db.DateTime, nullable=True)

    # Audit user foreign keys (pointing to users.id)
    # Using @declared_attr ensures unique per-table constraint names across MySQL schema
    @declared_attr
    def created_by(cls):
        return db.Column(
            db.Integer,
            db.ForeignKey('users.id', name=f'fk_{cls.__tablename__}_created_by', ondelete='SET NULL', use_alter=True),
            nullable=True
        )

    @declared_attr
    def updated_by(cls):
        return db.Column(
            db.Integer,
            db.ForeignKey('users.id', name=f'fk_{cls.__tablename__}_updated_by', ondelete='SET NULL', use_alter=True),
            nullable=True
        )

    @declared_attr
    def deleted_by(cls):
        return db.Column(
            db.Integer,
            db.ForeignKey('users.id', name=f'fk_{cls.__tablename__}_deleted_by', ondelete='SET NULL', use_alter=True),
            nullable=True
        )

    def soft_delete(self, user_id=None):
        """Soft deletes the record and updates audit metadata."""
        if user_id is None and has_request_context():
            try:
                from flask_login import current_user
                if current_user and current_user.is_authenticated:
                    user_id = current_user.id
            except Exception:
                pass

        self.is_deleted = True
        self.status = 'deactive'
        self.deleted_at = datetime.utcnow()
        self.deleted_by = user_id
        if user_id:
            self.updated_by = user_id

    def restore(self, user_id=None):
        """Restores a soft-deleted record back to active state."""
        if user_id is None and has_request_context():
            try:
                from flask_login import current_user
                if current_user and current_user.is_authenticated:
                    user_id = current_user.id
            except Exception:
                pass

        self.is_deleted = False
        self.status = 'active'
        self.deleted_at = None
        self.deleted_by = None
        if user_id:
            self.updated_by = user_id

    @classmethod
    def query_with_deleted(cls):
        """Query including soft-deleted records."""
        return db.session.query(cls).execution_options(include_deleted=True)

    @classmethod
    def query_trash(cls):
        """Query only soft-deleted records (for Admin Trash page)."""
        return (
            db.session.query(cls)
            .execution_options(include_deleted=True)
            .filter(cls.is_deleted.is_(True))
        )

    def to_dict(self):
        """Generic dictionary representation of model columns."""
        res = {}
        for col in self.__table__.columns:
            val = getattr(self, col.name)
            if isinstance(val, datetime):
                val = val.isoformat()
            res[col.name] = val
        return res


def register_base_model_events(app, session):
    """
    Registers SQLAlchemy event listeners for:
    1. Automatic audit user population (created_by, updated_by)
    2. Global transparent soft delete filtering
    """

    @event.listens_for(session, "before_flush")
    def _auto_fill_audit_users(sess, flush_context, instances):
        user_id = None
        if has_request_context():
            try:
                from flask_login import current_user
                if current_user and current_user.is_authenticated:
                    user_id = current_user.id
            except Exception:
                pass

        for obj in sess.new:
            if isinstance(obj, BaseModel):
                if user_id and obj.created_by is None:
                    obj.created_by = user_id
                if user_id and obj.updated_by is None:
                    obj.updated_by = user_id

        for obj in sess.dirty:
            if isinstance(obj, BaseModel):
                if user_id and not sess.is_modified(obj, include_collections=False):
                    continue
                if user_id and obj.updated_by is None:
                    obj.updated_by = user_id

    @event.listens_for(session, "do_orm_execute")
    def _add_soft_delete_filter(execute_state):
        # Automatically filter out soft-deleted records unless explicitly asked
        if (
            execute_state.is_orm_statement
            and not execute_state.is_relationship_load
            and not execute_state.execution_options.get("include_deleted", False)
        ):
            execute_state.statement = execute_state.statement.options(
                orm.with_loader_criteria(
                    BaseModel,
                    lambda cls: cls.is_deleted.is_(False),
                    include_aliases=True
                )
            )
