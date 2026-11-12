from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app.models.customers import Customer
from app.models.orders import Order
from app.services.customer_service import CustomerService, CustomerServiceError
from app.utils.access_control import permission_required


customers_bp = Blueprint('customers', __name__, url_prefix='/customers')


@customers_bp.route('/')
@login_required
@permission_required('customers.manage')
def index():
    search = request.args.get('q', '', type=str).strip()
    query = Customer.query.filter_by(is_deleted=False)
    if search:
        pattern = f'%{search}%'
        query = query.filter(
            Customer.name.ilike(pattern)
            | Customer.email.ilike(pattern)
            | Customer.phone.ilike(pattern)
        )

    pagination = query.order_by(Customer.name.asc()).paginate(
        page=request.args.get('page', 1, type=int),
        per_page=10,
        error_out=False
    )
    return render_template(
        'customers/index.html',
        customers=pagination.items,
        pagination=pagination,
        search=search
    )


@customers_bp.route('/new', methods=['GET', 'POST'])
@login_required
@permission_required('customers.manage')
def create():
    if request.method == 'POST':
        try:
            customer = CustomerService.create_customer(request.form, user_id=current_user.id)
            flash(f'Customer {customer.name} created.', 'success')
            return redirect(url_for('customers.detail', customer_id=customer.id))
        except CustomerServiceError as exc:
            flash(str(exc), 'danger')
    return render_template('customers/form.html', customer=None)


@customers_bp.route('/<int:customer_id>')
@login_required
@permission_required('customers.manage')
def detail(customer_id):
    customer = Customer.query.filter_by(id=customer_id, is_deleted=False).first_or_404()
    orders = customer.orders.order_by(Order.created_at.desc()).all()
    return render_template('customers/detail.html', customer=customer, orders=orders)


@customers_bp.route('/<int:customer_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('customers.manage')
def edit(customer_id):
    customer = Customer.query.filter_by(id=customer_id, is_deleted=False).first_or_404()
    if request.method == 'POST':
        try:
            customer = CustomerService.update_customer(
                customer_id,
                request.form,
                user_id=current_user.id
            )
            flash(f'Customer {customer.name} updated.', 'success')
            return redirect(url_for('customers.detail', customer_id=customer.id))
        except CustomerServiceError as exc:
            flash(str(exc), 'danger')
    return render_template('customers/form.html', customer=customer)


@customers_bp.route('/<int:customer_id>/delete', methods=['POST'])
@login_required
@permission_required('customers.manage')
def delete(customer_id):
    try:
        CustomerService.delete_customer(customer_id, user_id=current_user.id)
        flash('Customer moved to trash.', 'success')
    except CustomerServiceError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('customers.index'))
