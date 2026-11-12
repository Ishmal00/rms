from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel


class Notification(BaseModel):
    """A user-specific in-app notification."""
    __tablename__ = 'notifications'

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', name='fk_notifications_user_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(40), nullable=False, index=True)
    link = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    read_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()

    def __repr__(self):
        return f'<Notification {self.notification_type} for user={self.user_id}>'
