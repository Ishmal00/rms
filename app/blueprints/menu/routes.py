from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.menu import Category, MenuItem, SubCategory
from app.services.cache_service import cache
from app.services.status_service import StatusService, StatusServiceError
from app.services.audit_service import AuditService
from app.utils.access_control import permission_required

menu_bp = Blueprint('menu', __name__, url_prefix='/menu')


@menu_bp.route('/')
@login_required
@permission_required('menu.manage')
def index():
    page = request.args.get('page', 1, type=int)
    category_slug = request.args.get('category', '', type=str)
    search_query = request.args.get('q', '', type=str).strip()
    status = request.args.get('status', 'active', type=str)

    # Retrieve categories with caching
    categories = cache.get('categories:all')
    if not categories:
        cats = Category.query.filter_by(is_deleted=False).order_by(Category.display_order.asc(), Category.name.asc()).all()
        categories = [{'id': c.id, 'name': c.name, 'slug': c.slug, 'status': c.status} for c in cats]
        cache.set('categories:all', categories, timeout=300)

    # Build query
    query = MenuItem.query.filter_by(is_deleted=False)
    if status in ('active', 'deactive'):
        query = query.filter(MenuItem.status == status)

    selected_category = None
    if category_slug:
        selected_category = Category.query.filter_by(slug=category_slug).first()
        if selected_category:
            query = query.filter(MenuItem.category_id == selected_category.id)

    if search_query:
        query = query.filter(
            (MenuItem.name.ilike(f'%{search_query}%')) |
            (MenuItem.description.ilike(f'%{search_query}%'))
        )

    # Server-side pagination
    pagination = query.order_by(MenuItem.name.asc()).paginate(
        page=page,
        per_page=8,
        error_out=False
    )

    return render_template(
        'menu/index.html',
        pagination=pagination,
        items=pagination.items,
        categories=categories,
        selected_category=selected_category,
        search_query=search_query,
        selected_status=status
    )


@menu_bp.route('/items/<int:item_id>/toggle-status', methods=['POST'])
@login_required
@permission_required('menu.manage')
def toggle_item_status(item_id):
    item = MenuItem.query.filter_by(id=item_id, is_deleted=False).first_or_404()
    try:
        StatusService.toggle(item, current_user.id)
        cache.delete_pattern('dashboard:*')
        cache.delete_pattern('reports:*')
        cache.delete_pattern('menu:*')
        flash(f'Menu item status changed to {item.status}.', 'success')
    except StatusServiceError as exc:
        flash(str(exc), 'danger')
    return redirect(request.referrer or url_for('menu.index'))


@menu_bp.route('/categories/<int:category_id>/toggle-status', methods=['POST'])
@login_required
@permission_required('menu.manage')
def toggle_category_status(category_id):
    category = Category.query.filter_by(id=category_id, is_deleted=False).first_or_404()
    try:
        StatusService.toggle(category, current_user.id)
        cache.delete_pattern('categories:*')
        cache.delete_pattern('dashboard:*')
        cache.delete_pattern('reports:*')
        flash(f'Category status changed to {category.status}.', 'success')
    except StatusServiceError as exc:
        flash(str(exc), 'danger')
    return redirect(request.referrer or url_for('menu.index'))


@menu_bp.route('/api/data')
@login_required
@permission_required('menu.manage')
def menu_api():
    """Server-side DataTables JSON feed for menu catalog."""
    from app.utils.pagination import paginate_query
    category_slug = request.args.get('category', '', type=str).strip()

    query = MenuItem.query.filter_by(status='active', is_deleted=False)
    if category_slug:
        cat = Category.query.filter_by(slug=category_slug).first()
        if cat:
            query = query.filter(MenuItem.category_id == cat.id)

    def serialize_menu_item(m):
        return {
            'id': m.id,
            'name': m.name,
            'slug': m.slug,
            'category': m.category.name if m.category else '-',
            'base_price': f"${float(m.base_price):.2f}",
            'is_vegetarian': m.is_vegetarian,
            'is_spicy': m.is_spicy,
            'prep_time': f"{m.prep_time_minutes or 15} mins"
        }

    res = paginate_query(
        base_query=query,
        model=MenuItem,
        search_fields=['name', 'description'],
        default_sort=MenuItem.name.asc(),
        serializer_func=serialize_menu_item
    )
    return jsonify(res)
