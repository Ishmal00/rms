from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from app.models.inventory import InventoryItem, Supplier
from app.utils.access_control import permission_required

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')


@inventory_bp.route('/')
@login_required
@permission_required('inventory.manage')
def index():
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category', '', type=str)
    low_stock_only = request.args.get('low_stock', '', type=str) == '1'
    search = request.args.get('q', '', type=str).strip()

    query = InventoryItem.query

    if category:
        query = query.filter(InventoryItem.category == category)
    if low_stock_only:
        query = query.filter(InventoryItem.current_stock <= InventoryItem.minimum_stock)
    if search:
        query = query.filter(
            (InventoryItem.name.ilike(f'%{search}%')) |
            (InventoryItem.sku.ilike(f'%{search}%'))
        )

    pagination = query.order_by(InventoryItem.name.asc()).paginate(
        page=page,
        per_page=10,
        error_out=False
    )

    categories = [c[0] for c in InventoryItem.query.with_entities(InventoryItem.category).distinct().all()]

    return render_template(
        'inventory/index.html',
        pagination=pagination,
        items=pagination.items,
        categories=categories,
        selected_category=category,
        low_stock_only=low_stock_only,
        search_query=search
    )


@inventory_bp.route('/api/data')
@login_required
@permission_required('inventory.manage')
def inventory_api():
    """Server-side DataTables JSON feed for inventory items."""
    from app.utils.pagination import paginate_query
    category = request.args.get('category', '', type=str).strip()
    low_stock = request.args.get('low_stock', '', type=str) == '1'

    query = InventoryItem.query.filter_by(is_deleted=False)
    if category:
        query = query.filter(InventoryItem.category == category)
    if low_stock:
        query = query.filter(InventoryItem.current_stock <= InventoryItem.minimum_stock)

    def serialize_item(i):
        return {
            'id': i.id,
            'sku': i.sku,
            'name': i.name,
            'category': i.category,
            'current_stock': float(i.current_stock),
            'minimum_stock': float(i.minimum_stock),
            'reorder_quantity': float(i.reorder_quantity),
            'unit': i.unit,
            'unit_cost': f"${float(i.unit_cost):.2f}",
            'is_low_stock': i.current_stock <= i.minimum_stock,
            'supplier': i.supplier.name if i.supplier else '-'
        }

    res = paginate_query(
        base_query=query,
        model=InventoryItem,
        search_fields=['name', 'sku', 'category'],
        default_sort=InventoryItem.name.asc(),
        serializer_func=serialize_item
    )
    return jsonify(res)
