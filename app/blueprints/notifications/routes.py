from flask import Blueprint, flash, redirect, render_template, url_for, request
from flask_login import current_user, login_required
from app.models.notifications import Notification
from app.services.notification_service import NotificationService, NotificationServiceError
from app.services.status_service import StatusService, StatusServiceError
from app.utils.access_control import permission_required


notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')


@notifications_bp.route('/')
@login_required
@permission_required('notifications.manage')
def index():
    search = request.args.get('q', '', type=str).strip()
    notification_type = request.args.get('type', '', type=str).strip()
    read_status = request.args.get('read', '', type=str)
    status = request.args.get('status', '', type=str)
    query = Notification.query.filter_by(user_id=current_user.id, is_deleted=False)
    if search:
        pattern = f'%{search}%'
        query = query.filter(Notification.title.ilike(pattern) | Notification.message.ilike(pattern))
    if notification_type:
        query = query.filter(Notification.notification_type == notification_type)
    if read_status in ('read', 'unread'):
        query = query.filter(Notification.is_read.is_(read_status == 'read'))
    if status in ('active', 'deactive'):
        query = query.filter(Notification.status == status)
    pagination = query.order_by(Notification.created_at.desc(), Notification.id.desc()).paginate(
        page=request.args.get('page', 1, type=int),
        per_page=10,
        error_out=False
    )
    types = [
        row[0] for row in Notification.query.filter_by(user_id=current_user.id)
        .with_entities(Notification.notification_type).distinct().all()
    ]
    return render_template(
        'notifications/index.html',
        notifications=pagination.items,
        pagination=pagination,
        search=search,
        selected_type=notification_type,
        selected_read=read_status,
        selected_status=status,
        types=types
    )


@notifications_bp.route('/<int:notification_id>/read', methods=['POST'])
@login_required
@permission_required('notifications.manage')
def mark_as_read(notification_id):
    try:
        NotificationService.mark_as_read(notification_id, current_user.id)
        flash('Notification marked as read.', 'success')
    except NotificationServiceError as exc:
        flash(str(exc), 'warning')
    return redirect(url_for('notifications.index'))


@notifications_bp.route('/<int:notification_id>/toggle-status', methods=['POST'])
@login_required
@permission_required('notifications.manage')
def toggle_status(notification_id):
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id,
        is_deleted=False
    ).first_or_404()
    try:
        StatusService.toggle(notification, current_user.id)
        flash(f'Notification status changed to {notification.status}.', 'success')
    except StatusServiceError as exc:
        flash(str(exc), 'danger')
    return redirect(request.referrer or url_for('notifications.index'))
