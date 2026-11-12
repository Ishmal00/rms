from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models.kitchen import KitchenTicket
from app.services.order_service import OrderService, OrderError
from app.utils.access_control import role_required

kitchen_bp = Blueprint('kitchen', __name__, url_prefix='/kitchen')


@kitchen_bp.route('/')
@login_required
@role_required('kitchen')
def index():
    """Kitchen Display Screen (KDS) live ticket view."""
    pending_tickets = KitchenTicket.query.filter_by(kitchen_status='pending', is_deleted=False).order_by(KitchenTicket.created_at.asc()).all()
    preparing_tickets = KitchenTicket.query.filter_by(kitchen_status='preparing', is_deleted=False).order_by(KitchenTicket.prep_started_at.asc()).all()
    ready_tickets = KitchenTicket.query.filter_by(kitchen_status='ready', is_deleted=False).order_by(KitchenTicket.ready_at.asc()).all()

    return render_template(
        'kitchen/index.html',
        pending_tickets=pending_tickets,
        preparing_tickets=preparing_tickets,
        ready_tickets=ready_tickets
    )


@kitchen_bp.route('/tickets/<int:ticket_id>/status', methods=['POST'])
@login_required
@role_required('kitchen')
def update_ticket_status(ticket_id):
    """Progresses ticket state on the kitchen display."""
    target_status = request.form.get('status')
    ticket = KitchenTicket.query.filter_by(id=ticket_id, is_deleted=False).first_or_404()

    try:
        # Synchronize order status with kitchen status
        if ticket.order:
            OrderService.update_order_status(
                order_id=ticket.order.id,
                new_status=target_status,
                user_id=current_user.id,
                notes=f"Kitchen ticket #{ticket.ticket_number} advanced to {target_status}."
            )
            flash(f"Ticket #{ticket.ticket_number} updated to '{target_status}'.", 'success')
        else:
            if target_status == 'preparing':
                ticket.mark_preparing()
            elif target_status == 'ready':
                ticket.mark_ready()
            elif target_status == 'served':
                ticket.mark_served()
            ticket.save()
            flash(f"Ticket #{ticket.ticket_number} updated.", 'success')

    except OrderError as e:
        flash(f"Could not update kitchen status: {str(e)}", 'danger')

    return redirect(url_for('kitchen.index'))
