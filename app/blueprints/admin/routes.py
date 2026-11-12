from flask import Blueprint, render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from app.extensions import db
from app.models.auth import User, Role
from app.models.menu import MenuItem, Category
from app.models.tables import RestaurantTable
from app.models.inventory import InventoryItem
from app.utils.access_control import permission_required

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
    all_users = User.query.order_by(User.id.asc()).all()
    roles = Role.query.all()
    return render_template('admin/users.html', users=all_users, roles=roles)
