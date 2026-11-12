import json
import re

from flask import Blueprint, current_app, render_template, flash, redirect, url_for, request
from flask_login import login_required, current_user
from sqlalchemy import cast, func, literal, or_, select, union_all
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models.auth import User, Role
from app.models.base import BaseModel
from app.models.menu import MenuItem, Category
from app.models.tables import RestaurantTable
from app.models.inventory import InventoryItem
from app.models.settings import AuditLog
from app.services.cache_service import (
    invalidate_dashboard_cache,
    invalidate_inventory_cache,
    invalidate_menu_cache,
    invalidate_report_cache,
    invalidate_settings_cache,
)
from app.utils.access_control import permission_required, role_required
from app.services.status_service import StatusService, StatusServiceError

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _trash_model_registry():
    import app.models

    excluded_models = {'User', 'Role', 'Permission', 'RolePermission'}
    registry = {}
    model_classes = [
        getattr(app.models, name)
        for name in app.models.__all__
        if isinstance(getattr(app.models, name), type)
    ]
    for model in model_classes:
        if (
            not issubclass(model, BaseModel)
            or model is BaseModel
            or model.__name__ in excluded_models
        ):
            continue
        entity_type = re.sub(r'(?<!^)(?=[A-Z])', '_', model.__name__).lower()
        if model is RestaurantTable:
            entity_type = 'table'
        registry[entity_type] = model
    return registry


@admin_bp.route('/trash')
@login_required
@role_required('admin')
def trash():
    """Browse deleted records by model type; authentication records stay protected."""
    registry = _trash_model_registry()
    search = request.args.get('q', '', type=str).strip()
    selected_entity = request.args.get('entity_type', '', type=str)
    page = request.args.get('page', 1, type=int)
    per_page = 20
    selects = []

    for entity_type, model in registry.items():
        if selected_entity and selected_entity != entity_type:
            continue

        string_columns = [
            getattr(model, column.name)
            for column in model.__table__.columns
            if getattr(column.type, 'python_type', None) is str
        ]
        statement = select(
            literal(entity_type).label('entity_type'),
            literal(model.__name__).label('entity_label'),
            model.id.label('record_id'),
            func.coalesce(
                *[
                    cast(getattr(model, field), db.String)
                    for field in (
                        'name', 'title', 'username', 'full_name', 'employee_code',
                        'table_number', 'setting_key', 'sku', 'reference_no',
                        'number', 'code', 'slug'
                    )
                    if hasattr(model, field)
                ],
                cast(model.id, db.String)
            ).label('record_name'),
            model.deleted_at.label('deleted_at'),
            model.deleted_by.label('deleted_by'),
        ).where(model.is_deleted.is_(True))

        if search:
            search_conditions = [column.ilike(f'%{search}%') for column in string_columns]
            if search.isdigit():
                search_conditions.append(model.id == int(search))
            if search_conditions:
                statement = statement.where(or_(*search_conditions))
            else:
                continue
        selects.append(statement)

    if selects:
        trash_rows = union_all(*selects).subquery('trash_rows')
        trash_query = db.session.query(trash_rows).order_by(
            trash_rows.c.deleted_at.desc(),
            trash_rows.c.entity_label.asc(),
            trash_rows.c.record_id.asc()
        ).execution_options(include_deleted=True)
        pagination = trash_query.paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        rows = pagination.items
    else:
        pagination = None
        rows = []

    deleted_by_ids = {row.deleted_by for row in rows if row.deleted_by is not None}
    deleted_users = User.query_with_deleted().filter(User.id.in_(deleted_by_ids)).all()
    users_by_id = {user.id: user for user in deleted_users}
    grouped_trash = {}
    for row in rows:
        grouped_trash.setdefault(row.entity_label, []).append({
            'entity_type': row.entity_type,
            'id': row.record_id,
            'name': row.record_name,
            'deleted_at': row.deleted_at,
            'deleted_by': users_by_id.get(row.deleted_by),
            'deleted_by_id': row.deleted_by,
        })

    return render_template(
        'admin/trash.html',
        grouped_trash=grouped_trash,
        registry=registry,
        entity_options=[(key, model.__name__) for key, model in registry.items()],
        pagination=pagination,
        search=search,
        selected_entity=selected_entity
    )


@admin_bp.route('/restore/<entity_type>/<int:item_id>', methods=['POST'])
@login_required
@role_required('admin')
def restore_item(entity_type, item_id):
    """Restores a registered soft-deleted record and records the action atomically."""
    model_class = _trash_model_registry().get(entity_type)
    if not model_class:
        flash('Invalid entity type for restoration.', 'danger')
        return redirect(url_for('admin.trash'))

    item = model_class.query_with_deleted().filter_by(id=item_id).first_or_404()
    item.restore(user_id=current_user.id)
    db.session.add(AuditLog(
        user_id=current_user.id,
        action='RESTORE',
        target_entity=model_class.__name__,
        target_id=item.id,
        details_json=json.dumps({'entity_type': entity_type}),
        ip_address=request.remote_addr,
        created_by=current_user.id
    ))
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception(
            'Failed to restore %s #%s',
            model_class.__name__,
            item_id
        )
        flash('The record could not be restored. No changes were saved.', 'danger')
        return redirect(url_for('admin.trash'))

    invalidate_dashboard_cache()
    invalidate_report_cache()
    if model_class in (MenuItem, Category) or model_class.__name__ == 'SubCategory':
        invalidate_menu_cache()
    if model_class is InventoryItem or model_class.__name__ in ('Supplier', 'StockMovement'):
        invalidate_inventory_cache()
    if model_class.__name__ == 'SystemSetting':
        invalidate_settings_cache()

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
