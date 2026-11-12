import json
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models.orders import Order, OrderType
from app.models.tables import RestaurantTable
from app.models.menu import Category, MenuItem
from app.models.customers import Customer
from app.services.order_service import OrderService, OrderError
from app.utils.access_control import permission_required

orders_bp = Blueprint('orders', __name__, url_prefix='/orders')


@orders_bp.route('/')
@login_required
@permission_required('orders.manage')
def index():
    status = request.args.get('status', '', type=str)
    order_type = request.args.get('type', '', type=str)

    query = Order.query.filter_by(is_deleted=False)

    if status:
        query = query.filter(Order.order_status == status)
    if order_type:
        ot = OrderType.query.filter_by(slug=order_type).first()
        if ot:
            query = query.filter(Order.order_type_id == ot.id)

    orders = query.order_by(Order.created_at.desc()).all()
    order_types = OrderType.query.filter_by(status='active', is_deleted=False).all()

    return render_template(
        'orders/index.html',
        orders=orders,
        order_types=order_types,
        selected_status=status,
        selected_type=order_type
    )


@orders_bp.route('/pos')
@login_required
@permission_required('orders.pos')
def pos():
    """Point of Sale (POS) Order Entry Screen."""
    tables = RestaurantTable.query.filter_by(status='active', is_deleted=False).order_by(RestaurantTable.table_number.asc()).all()
    order_types = OrderType.query.filter_by(status='active', is_deleted=False).all()
    categories = Category.query.filter_by(status='active', is_deleted=False).order_by(Category.display_order.asc()).all()
    menu_items = MenuItem.query.filter_by(status='active', is_deleted=False).order_by(MenuItem.name.asc()).all()
    customers = Customer.query.filter_by(status='active', is_deleted=False).order_by(Customer.name.asc()).all()

    return render_template(
        'orders/pos.html',
        tables=tables,
        order_types=order_types,
        categories=categories,
        menu_items=menu_items,
        customers=customers
    )


@orders_bp.route('/place', methods=['POST'])
@login_required
@permission_required('orders.pos')
def place():
    """Places an order atomically via OrderService."""
    order_type_slug = request.form.get('order_type_slug', 'dine-in')
    table_id = request.form.get('table_id', type=int) or None
    customer_id = request.form.get('customer_id', type=int) or None
    special_notes = request.form.get('special_notes')
    coupon_code = request.form.get('coupon_code')
    items_json = request.form.get('items_json')

    try:
        items_data = json.loads(items_json) if items_json else []
    except Exception:
        items_data = []

    if not items_data:
        flash('Please select at least one item to place an order.', 'danger')
        return redirect(url_for('orders.pos'))

    try:
        order = OrderService.place_order(
            order_type_slug=order_type_slug,
            items_data=items_data,
            table_id=table_id,
            customer_id=customer_id,
            user_id=current_user.id,
            special_notes=special_notes,
            coupon_code=coupon_code
        )
        flash(f"Order #{order.order_number} placed successfully! Kitchen ticket generated.", 'success')

        # If invoice was created, redirect to invoice/payment screen
        if order.invoice:
            return redirect(url_for('billing.invoice_detail', invoice_id=order.invoice.id))
        return redirect(url_for('orders.index'))

    except OrderError as e:
        flash(f"Failed to place order: {str(e)}", 'danger')
        return redirect(url_for('orders.pos'))


@orders_bp.route('/<int:order_id>/cancel', methods=['POST'])
@login_required
@permission_required('orders.manage')
def cancel(order_id):
    """Cancels an order atomically via OrderService."""
    reason = request.form.get('reason', 'Cancelled from orders console')
    try:
        OrderService.cancel_order(order_id=order_id, user_id=current_user.id, reason=reason)
        flash(f"Order #{order_id} has been cancelled. Table freed and stock restored.", 'info')
    except OrderError as e:
        flash(f"Could not cancel order: {str(e)}", 'danger')

    return redirect(url_for('orders.index'))


@orders_bp.route('/<int:order_id>/status', methods=['POST'])
@login_required
@permission_required('orders.manage')
def update_status(order_id):
    """Updates order status via OrderService."""
    new_status = request.form.get('status')
    notes = request.form.get('notes')
    try:
        OrderService.update_order_status(order_id=order_id, new_status=new_status, user_id=current_user.id, notes=notes)
        flash(f"Order #{order_id} updated to '{new_status}'.", 'success')
    except OrderError as e:
        flash(f"Could not update status: {str(e)}", 'danger')

    return redirect(request.referrer or url_for('orders.index'))


@orders_bp.route('/api/data')
@login_required
@permission_required('orders.manage')
def orders_api():
    """Server-side DataTables JSON feed for orders."""
    from app.utils.pagination import paginate_query
    status = request.args.get('status', '').strip()
    order_type = request.args.get('type', '').strip()

    base_query = Order.query.filter_by(is_deleted=False)
    if status:
        base_query = base_query.filter(Order.order_status == status)
    if order_type:
        ot = OrderType.query.filter_by(slug=order_type).first()
        if ot:
            base_query = base_query.filter(Order.order_type_id == ot.id)

    def serialize_order(o):
        return {
            'id': o.id,
            'order_number': o.order_number,
            'type': o.order_type.name if o.order_type else '-',
            'table': o.table.table_number if o.table else ('Takeaway' if o.order_type and o.order_type.slug == 'takeaway' else 'Delivery'),
            'customer': o.customer.name if o.customer else 'Walk-in Guest',
            'status': o.order_status,
            'total_amount': f"${float(o.total_amount or 0):.2f}",
            'created_at': o.created_at.strftime('%b %d, %Y %H:%M') if o.created_at else '-',
            'invoice_id': o.invoice.id if o.invoice else None
        }

    res = paginate_query(
        base_query=base_query,
        model=Order,
        search_fields=['order_number', 'special_notes'],
        default_sort=Order.created_at.desc(),
        serializer_func=serialize_order
    )
    return jsonify(res)
