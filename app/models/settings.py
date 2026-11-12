from app.extensions import db
from app.models.base import BaseModel


class SystemSetting(BaseModel):
    """Dynamic operational system settings store."""
    __tablename__ = 'system_settings'

    setting_key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    setting_value = db.Column(db.Text, nullable=False)
    setting_type = db.Column(db.String(30), default='string', nullable=False)  # string, number, boolean, json
    description = db.Column(db.String(255), nullable=True)
    is_public = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<SystemSetting {self.setting_key}={self.setting_value}>"


class AuditLog(BaseModel):
    """Audit log for critical security and operational events."""
    __tablename__ = 'audit_logs'

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', name='fk_audit_logs_user_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    action = db.Column(db.String(50), nullable=False, index=True)  # CREATE, UPDATE, DELETE, LOGIN, etc.
    target_entity = db.Column(db.String(50), nullable=False)       # Order, Invoice, User, etc.
    target_id = db.Column(db.Integer, nullable=True)
    details_json = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f"<AuditLog {self.action} on {self.target_entity}:{self.target_id} by user={self.user_id}>"
