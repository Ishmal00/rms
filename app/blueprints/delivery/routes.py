from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models.delivery import Delivery, DeliveryAgent, DeliveryTracking
from app.services.delivery_service import DeliveryService, DeliveryServiceError
from app.services.audit_service import AuditService

delivery_bp = Blueprint('delivery', __name__, url_prefix='/delivery')


@delivery_bp.route('/')
@login_required
def index():
    deliveries = Delivery.query.order_by(Delivery.created_at.desc()).all()
    agents = DeliveryAgent.query.order_by(DeliveryAgent.name).all()
    active_deliveries = [d for d in deliveries if d.delivery_status not in ['delivered', 'failed']]
    completed_deliveries = [d for d in deliveries if d.delivery_status in ['delivered', 'failed']]

    return render_template(
        'delivery/index.html',
        deliveries=deliveries,
        active_deliveries=active_deliveries,
        completed_deliveries=completed_deliveries,
        agents=agents
    )


@delivery_bp.route('/assign/<int:delivery_id>', methods=['POST'])
@login_required
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
def toggle_agent(agent_id):
    agent = DeliveryAgent.query.get_or_404(agent_id)
    agent.is_available = not agent.is_available
    agent.updated_by = current_user.id
    db.session.commit()
    status_str = "Available" if agent.is_available else "Off-duty"
    flash(f"Agent {agent.name} is now {status_str}.", "info")
    return redirect(url_for('delivery.index'))
