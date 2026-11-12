from datetime import datetime
from app.extensions import db
from app.models.auth import User
from app.models.notifications import Notification


class NotificationServiceError(Exception):
    """Raised when a notification operation fails."""


class NotificationService:
    @staticmethod
    def create_for_user(user_id, title, message, notification_type, link=None, created_by=None):
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            link=link,
            created_by=created_by
        )
        db.session.add(notification)
        return notification

    @staticmethod
    def create_for_all(title, message, notification_type, link=None, created_by=None):
        recipients = User.query.filter_by(status='active', is_deleted=False).all()
        notifications = [
            Notification(
                user_id=user.id,
                title=title,
                message=message,
                notification_type=notification_type,
                link=link,
                created_by=created_by
            )
            for user in recipients
        ]
        db.session.add_all(notifications)
        return notifications

    @staticmethod
    def unread_count(user_id):
        return Notification.query.filter_by(user_id=user_id, is_read=False).count()

    @staticmethod
    def recent_for_user(user_id, limit=5):
        return (
            Notification.query.filter_by(user_id=user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def list_for_user(user_id):
        return (
            Notification.query.filter_by(user_id=user_id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .all()
        )

    @staticmethod
    def mark_as_read(notification_id, user_id):
        notification = Notification.query.filter_by(
            id=notification_id,
            user_id=user_id,
            is_read=False
        ).first()
        if not notification:
            raise NotificationServiceError('Unread notification not found.')

        try:
            notification.is_read = True
            notification.read_at = datetime.utcnow()
            notification.updated_by = user_id
            db.session.commit()
            return notification
        except Exception as exc:
            db.session.rollback()
            raise NotificationServiceError(f'Failed to mark notification as read: {exc}') from exc
