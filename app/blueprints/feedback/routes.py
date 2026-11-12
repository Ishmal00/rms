from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.feedback import CustomerFeedback
from app.models.customers import Customer
from app.models.orders import Order
from app.services.feedback_service import FeedbackService, FeedbackServiceError
from app.services.audit_service import AuditService
from app.services.status_service import StatusService, StatusServiceError
from app.utils.access_control import permission_required

feedback_bp = Blueprint('feedback', __name__, url_prefix='/feedback')


@feedback_bp.route('/')
@login_required
@permission_required('feedback.manage')
def index():
    search = request.args.get('q', '', type=str).strip()
    rating = request.args.get('rating', type=int)
    status = request.args.get('status', '', type=str)
    query = CustomerFeedback.query.filter_by(is_deleted=False)
    if search:
        pattern = f'%{search}%'
        query = query.filter(
            CustomerFeedback.comments.ilike(pattern)
            | CustomerFeedback.response_notes.ilike(pattern)
            | CustomerFeedback.customer.has(Customer.name.ilike(pattern))
        )
    if rating and 1 <= rating <= 5:
        query = query.filter(CustomerFeedback.overall_rating >= rating, CustomerFeedback.overall_rating < rating + 1)
    if status in ('active', 'deactive'):
        query = query.filter(CustomerFeedback.status == status)
    pagination = query.order_by(CustomerFeedback.created_at.desc()).paginate(
        page=request.args.get('page', 1, type=int),
        per_page=10,
        error_out=False
    )
    feedbacks = pagination.items
    stats = FeedbackService.get_feedback_statistics()
    customers = Customer.query.order_by(Customer.name).all()
    recent_orders = Order.query.order_by(Order.id.desc()).limit(30).all()

    return render_template(
        'feedback/index.html',
        feedbacks=feedbacks,
        pagination=pagination,
        search=search,
        selected_rating=rating,
        selected_status=status,
        stats=stats,
        customers=customers,
        recent_orders=recent_orders
    )


@feedback_bp.route('/create', methods=['POST'])
@login_required
@permission_required('feedback.manage')
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
@permission_required('feedback.manage')
def respond_feedback(feedback_id):
    notes = request.form.get('response_notes', '')
    try:
        fb = FeedbackService.respond_to_feedback(feedback_id, notes, user_id=current_user.id)
        flash(f"Response saved for feedback #{fb.id}.", "success")
        AuditService.log('RESPOND_FEEDBACK', 'CustomerFeedback', fb.id, "Staff response added", user_id=current_user.id)
    except FeedbackServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for('feedback.index'))


@feedback_bp.route('/<int:feedback_id>/toggle-status', methods=['POST'])
@login_required
@permission_required('feedback.manage')
def toggle_status(feedback_id):
    feedback = CustomerFeedback.query.filter_by(id=feedback_id, is_deleted=False).first_or_404()
    try:
        StatusService.toggle(feedback, current_user.id, entity_name='CustomerFeedback')
        flash(f'Feedback status changed to {feedback.status}.', 'success')
    except StatusServiceError as exc:
        flash(str(exc), 'danger')
    return redirect(request.referrer or url_for('feedback.index'))
