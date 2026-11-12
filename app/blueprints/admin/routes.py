from flask import Blueprint, render_template, flash, redirect, url_for, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models.auth import User, Role
from app.models.menu import MenuItem, Category
from app.models.tables import RestaurantTable
from app.models.inventory import InventoryItem
from app.utils.access_control import permission_required
from app.services.status_service import StatusService, StatusServiceError

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/trash')
@login_required
@permission_required('admin.trash')
def trash():
    """Admin Trash & Recovery console for soft-deleted entities."""
    deleted_menu_items = MenuItem.query_trash().all()
    deleted_tables = RestaurantTable.query_trash().all()
    deleted_inventory = InventoryItem.query_trash().all()
    deleted_categories = Category.query_trash().all()

    return render_template(
        'admin/trash.html',
        menu_items=deleted_menu_items,
        tables=deleted_tables,
        inventory_items=deleted_inventory,
        categories=deleted_categories
    )


@admin_bp.route('/restore/<entity_type>/<int:item_id>', methods=['POST'])
@login_required
@permission_required('admin.trash')
def restore_item(entity_type, item_id):
    """Restores a soft-deleted record back to active status."""
    model_map = {
        'menu_item': MenuItem,
        'category': Category,
        'table': RestaurantTable,
        'inventory_item': InventoryItem,
    }

    model_class = model_map.get(entity_type)
    if not model_class:
        flash('Invalid entity type for restoration.', 'danger')
        return redirect(url_for('admin.trash'))

    item = model_class.query_with_deleted().filter_by(id=item_id).first_or_404()
    item.restore(user_id=current_user.id)
    db.session.commit()

    flash(f'{model_class.__name__} #{item_id} has been restored successfully.', 'success')
    return redirect(url_for('admin.trash'))


@admin_bp.route('/users')
@login_required
@permission_required('auth.manage')
def users():
    """Admin User & Role listing."""
    search = request.args.get('q', '', type=str).strip()
    role_id = request.args.get('role_id', type=int)
    status = request.args.get('status', '', type=str)
    query = User.query.filter_by(is_deleted=False)
    if search:
        pattern = f'%{search}%'
        query = query.filter(
            User.username.ilike(pattern) | User.full_name.ilike(pattern) | User.email.ilike(pattern)
        )
    if role_id:
        query = query.filter(User.role_id == role_id)
    if status in ('active', 'deactive'):
        query = query.filter(User.status == status)
    pagination = query.order_by(User.id.asc()).paginate(
        page=request.args.get('page', 1, type=int),
        per_page=10,
        error_out=False
    )
    roles = Role.query.all()
    return render_template(
        'admin/users.html',
        users=pagination.items,
        roles=roles,
        pagination=pagination,
        search=search,
        selected_role=role_id,
        selected_status=status
    )


@admin_bp.route('/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@permission_required('auth.manage')
def toggle_user_status(user_id):
    user = User.query.filter_by(id=user_id, is_deleted=False).first_or_404()
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('admin.users'))
    try:
        StatusService.toggle(user, current_user.id, entity_name='User')
        flash(f'User status changed to {user.status}.', 'success')
    except StatusServiceError as exc:
        flash(str(exc), 'danger')
    return redirect(request.referrer or url_for('admin.users'))
