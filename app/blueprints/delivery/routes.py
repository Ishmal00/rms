from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models.delivery import Delivery, DeliveryAgent, DeliveryTracking
from app.models.orders import Order
from app.models.customers import Customer
from app.services.delivery_service import DeliveryService, DeliveryServiceError
from app.services.audit_service import AuditService
from app.services.status_service import StatusService, StatusServiceError
from app.utils.access_control import permission_required

delivery_bp = Blueprint('delivery', __name__, url_prefix='/delivery')


@delivery_bp.route('/')
@login_required
@permission_required('delivery.manage')
def index():
    search = request.args.get('q', '', type=str).strip()
    delivery_status = request.args.get('delivery_status', '', type=str)
    record_status = request.args.get('status', '', type=str)
    delivery_query = Delivery.query.filter_by(is_deleted=False)
    if search:
        pattern = f'%{search}%'
        delivery_query = delivery_query.filter(
            Delivery.delivery_notes.ilike(pattern)
            | Delivery.order.has(Order.order_number.ilike(pattern))
            | Delivery.order.has(Order.customer.has(Customer.name.ilike(pattern)))
        )
    if delivery_status:
        delivery_query = delivery_query.filter(Delivery.delivery_status == delivery_status)
    if record_status in ('active', 'deactive'):
        delivery_query = delivery_query.filter(Delivery.status == record_status)
    delivery_pagination = delivery_query.order_by(Delivery.created_at.desc()).paginate(
        page=request.args.get('page', 1, type=int),
        per_page=10,
        error_out=False
    )

    agent_search = request.args.get('agent_q', '', type=str).strip()
    agent_status = request.args.get('agent_status', '', type=str)
    agent_query = DeliveryAgent.query.filter_by(is_deleted=False)
    if agent_search:
        pattern = f'%{agent_search}%'
        agent_query = agent_query.filter(
            DeliveryAgent.name.ilike(pattern) | DeliveryAgent.phone.ilike(pattern)
        )
    if agent_status in ('active', 'deactive'):
        agent_query = agent_query.filter(DeliveryAgent.status == agent_status)
    agent_pagination = agent_query.order_by(DeliveryAgent.name).paginate(
        page=request.args.get('agent_page', 1, type=int),
        per_page=8,
        error_out=False
    )
    deliveries = delivery_pagination.items
    agents = agent_pagination.items
    active_deliveries = [d for d in deliveries if d.delivery_status not in ['delivered', 'failed']]
    completed_deliveries = [d for d in deliveries if d.delivery_status in ['delivered', 'failed']]

    return render_template(
        'delivery/index.html',
        deliveries=deliveries,
        active_deliveries=active_deliveries,
        completed_deliveries=completed_deliveries,
        agents=agents,
        delivery_pagination=delivery_pagination,
        agent_pagination=agent_pagination,
        search=search,
        delivery_status=delivery_status,
        record_status=record_status,
        agent_search=agent_search,
        agent_status=agent_status
    )


@delivery_bp.route('/<int:delivery_id>/toggle-status', methods=['POST'])
@login_required
@permission_required('delivery.manage')
def toggle_delivery_status(delivery_id):
    delivery = Delivery.query.filter_by(id=delivery_id, is_deleted=False).first_or_404()
    try:
        StatusService.toggle(delivery, current_user.id)
        flash(f'Delivery record status changed to {delivery.status}.', 'success')
    except StatusServiceError as exc:
        flash(str(exc), 'danger')
    return redirect(request.referrer or url_for('delivery.index'))


@delivery_bp.route('/agents/<int:agent_id>/toggle-status', methods=['POST'])
@login_required
@permission_required('delivery.manage')
def toggle_agent_status(agent_id):
    agent = DeliveryAgent.query.filter_by(id=agent_id, is_deleted=False).first_or_404()
    try:
        StatusService.toggle(agent, current_user.id, entity_name='DeliveryAgent')
        flash(f'Driver status changed to {agent.status}.', 'success')
    except StatusServiceError as exc:
        flash(str(exc), 'danger')
    return redirect(request.referrer or url_for('delivery.index'))


@delivery_bp.route('/assign/<int:delivery_id>', methods=['POST'])
@login_required
@permission_required('delivery.manage')
def assign_agent(delivery_id):
    agent_id = request.form.get('agent_id', type=int)
    try:
        delivery = DeliveryService.assign_agent(delivery_id, agent_id, user_id=current_user.id)
        flash(f"Order #{delivery.order.order_number} assigned to {delivery.delivery_agent.name}.", "success")
        AuditService.log('ASSIGN_DELIVERY', 'Delivery', delivery.id, f"Agent ID {agent_id}", user_id=current_user.id)
    except DeliveryServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for('delivery.index'))


@delivery_bp.route('/status/<int:delivery_id>', methods=['POST'])
@login_required
@permission_required('delivery.manage')
def update_status(delivery_id):
    new_status = request.form.get('status')
    notes = request.form.get('notes', '')
    try:
        delivery = DeliveryService.advance_delivery_status(
            delivery_id, new_status, notes=notes, user_id=current_user.id
        )
        flash(f"Delivery for Order #{delivery.order.order_number} updated to '{new_status}'.", "success")
        AuditService.log('UPDATE_DELIVERY_STATUS', 'Delivery', delivery.id, f"Status: {new_status}", user_id=current_user.id)
    except DeliveryServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for('delivery.index'))


@delivery_bp.route('/agent/toggle/<int:agent_id>', methods=['POST'])
@login_required
@permission_required('delivery.manage')
def toggle_agent(agent_id):
    agent = DeliveryAgent.query.get_or_404(agent_id)
    agent.is_available = not agent.is_available
    agent.updated_by = current_user.id
    db.session.commit()
    status_str = "Available" if agent.is_available else "Off-duty"
    AuditService.log(
        'TOGGLE_DELIVERY_AVAILABILITY',
        'DeliveryAgent',
        agent.id,
        f'Availability: {status_str}',
        user_id=current_user.id
    )
    flash(f"Agent {agent.name} is now {status_str}.", "info")
    return redirect(url_for('delivery.index'))
