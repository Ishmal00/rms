from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from app.services.notification_service import NotificationService, NotificationServiceError


notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')


@notifications_bp.route('/')
@login_required
def index():
    notifications = NotificationService.list_for_user(current_user.id)
    return render_template('notifications/index.html', notifications=notifications)


@notifications_bp.route('/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_as_read(notification_id):
    try:
        NotificationService.mark_as_read(notification_id, current_user.id)
        flash('Notification marked as read.', 'success')
    except NotificationServiceError as exc:
        flash(str(exc), 'warning')
    return redirect(url_for('notifications.index'))
