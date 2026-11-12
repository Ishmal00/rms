from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.feedback import CustomerFeedback
from app.models.customers import Customer
from app.models.orders import Order
from app.services.feedback_service import FeedbackService, FeedbackServiceError
from app.services.audit_service import AuditService

feedback_bp = Blueprint('feedback', __name__, url_prefix='/feedback')


@feedback_bp.route('/')
@login_required
def index():
    feedbacks = CustomerFeedback.query.order_by(CustomerFeedback.created_at.desc()).all()
    stats = FeedbackService.get_feedback_statistics()
    customers = Customer.query.order_by(Customer.name).all()
    recent_orders = Order.query.order_by(Order.id.desc()).limit(30).all()

    return render_template(
        'feedback/index.html',
        feedbacks=feedbacks,
        stats=stats,
        customers=customers,
        recent_orders=recent_orders
    )


@feedback_bp.route('/create', methods=['POST'])
@login_required
def create_feedback():
    customer_id = request.form.get('customer_id', type=int)
    order_id = request.form.get('order_id', type=int)
    food_rating = request.form.get('food_rating', type=int)
    service_rating = request.form.get('service_rating', type=int)
    ambience_rating = request.form.get('ambience_rating', type=int)
    comments = request.form.get('comments', '')

    try:
        fb = FeedbackService.submit_feedback(
            food_rating=food_rating,
            service_rating=service_rating,
            ambience_rating=ambience_rating,
            customer_id=customer_id if customer_id else None,
            order_id=order_id if order_id else None,
            comments=comments,
            user_id=current_user.id
        )
        flash(f"Feedback submitted with rating {fb.overall_rating}/5.00.", "success")
        AuditService.log('SUBMIT_FEEDBACK', 'CustomerFeedback', fb.id, f"Rating: {fb.overall_rating}", user_id=current_user.id)
    except FeedbackServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for('feedback.index'))


@feedback_bp.route('/respond/<int:feedback_id>', methods=['POST'])
@login_required
def respond_feedback(feedback_id):
    notes = request.form.get('response_notes', '')
    try:
        fb = FeedbackService.respond_to_feedback(feedback_id, notes, user_id=current_user.id)
        flash(f"Response saved for feedback #{fb.id}.", "success")
        AuditService.log('RESPOND_FEEDBACK', 'CustomerFeedback', fb.id, "Staff response added", user_id=current_user.id)
    except FeedbackServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for('feedback.index'))
