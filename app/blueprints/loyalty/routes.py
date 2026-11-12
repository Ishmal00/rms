from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.customers import Customer
from app.models.loyalty import LoyaltyProgram, LoyaltyTransaction, Reward
from app.services.loyalty_service import LoyaltyService, LoyaltyServiceError
from app.services.audit_service import AuditService
from app.services.status_service import StatusService, StatusServiceError
from app.utils.access_control import permission_required

loyalty_bp = Blueprint('loyalty', __name__, url_prefix='/loyalty')


@loyalty_bp.route('/')
@login_required
@permission_required('loyalty.manage')
def index():
    search = request.args.get('q', '', type=str).strip()
    status = request.args.get('status', '', type=str)
    reward_type = request.args.get('reward_type', '', type=str)
    transaction_type = request.args.get('transaction_type', '', type=str)

    tier_query = LoyaltyProgram.query.filter_by(is_deleted=False)
    reward_query = Reward.query.filter_by(is_deleted=False)
    customer_query = Customer.query.filter_by(is_deleted=False)
    tx_query = LoyaltyTransaction.query.filter_by(is_deleted=False)
    if search:
        pattern = f'%{search}%'
        tier_query = tier_query.filter(
            LoyaltyProgram.tier_name.ilike(pattern)
            | LoyaltyProgram.perks_description.ilike(pattern)
        )
        reward_query = reward_query.filter(
            Reward.title.ilike(pattern) | Reward.reward_type.ilike(pattern)
        )
        customer_query = customer_query.filter(
            Customer.name.ilike(pattern) | Customer.phone.ilike(pattern) | Customer.email.ilike(pattern)
        )
        tx_query = tx_query.filter(
            LoyaltyTransaction.notes.ilike(pattern)
            | LoyaltyTransaction.customer.has(Customer.name.ilike(pattern))
        )
    if status in ('active', 'deactive'):
        tier_query = tier_query.filter(LoyaltyProgram.status == status)
        reward_query = reward_query.filter(Reward.status == status)
        customer_query = customer_query.filter(Customer.status == status)
        tx_query = tx_query.filter(LoyaltyTransaction.status == status)
    if reward_type:
        reward_query = reward_query.filter(Reward.reward_type == reward_type)
    if transaction_type:
        tx_query = tx_query.filter(LoyaltyTransaction.transaction_type == transaction_type)

    def page(query, key, order):
        return query.order_by(order).paginate(
            page=request.args.get(key, 1, type=int),
            per_page=8,
            error_out=False
        )

    tier_pagination = page(tier_query, 'tier_page', LoyaltyProgram.min_spend.asc())
    reward_pagination = page(reward_query, 'reward_page', Reward.points_required.asc())
    customer_pagination = page(customer_query, 'customer_page', Customer.loyalty_points.desc())
    transaction_pagination = page(tx_query, 'transaction_page', LoyaltyTransaction.created_at.desc())
    tiers = tier_pagination.items
    rewards = reward_pagination.items
    customers = customer_pagination.items
    recent_txs = transaction_pagination.items
    redeem_customers = Customer.query.filter_by(status='active').order_by(Customer.name).all()
    redeem_rewards = Reward.query.filter_by(status='active', is_active=True).order_by(Reward.points_required).all()

    return render_template(
        'loyalty/index.html',
        tiers=tiers,
        rewards=rewards,
        customers=customers,
        recent_txs=recent_txs,
        tier_pagination=tier_pagination,
        reward_pagination=reward_pagination,
        customer_pagination=customer_pagination,
        transaction_pagination=transaction_pagination,
        redeem_customers=redeem_customers,
        redeem_rewards=redeem_rewards,
        search=search,
        selected_status=status,
        selected_reward_type=reward_type,
        selected_transaction_type=transaction_type
    )


@loyalty_bp.route('/redeem-reward', methods=['POST'])
@login_required
@permission_required('loyalty.manage')
def redeem_reward():
    customer_id = request.form.get('customer_id', type=int)
    reward_id = request.form.get('reward_id', type=int)

    try:
        reward, tx = LoyaltyService.redeem_reward(customer_id, reward_id, user_id=current_user.id)
        flash(f"Redeemed '{reward.title}' for {tx.customer.name}! Remaining points: {tx.customer.loyalty_points}.", "success")
        AuditService.log('REDEEM_REWARD', 'Customer', customer_id, f"Reward: {reward.title}", user_id=current_user.id)
    except LoyaltyServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for('loyalty.index'))


@loyalty_bp.route('/<string:entity_type>/<int:record_id>/toggle-status', methods=['POST'])
@login_required
@permission_required('loyalty.manage')
def toggle_status(entity_type, record_id):
    models = {
        'tier': LoyaltyProgram,
        'reward': Reward,
        'customer': Customer,
        'transaction': LoyaltyTransaction
    }
    model = models.get(entity_type)
    if model is None:
        flash('Invalid loyalty record type.', 'danger')
        return redirect(url_for('loyalty.index'))
    record = model.query.filter_by(id=record_id, is_deleted=False).first_or_404()
    try:
        StatusService.toggle(record, current_user.id, entity_name=model.__name__)
        flash(f'{model.__name__} status changed to {record.status}.', 'success')
    except StatusServiceError as exc:
        flash(str(exc), 'danger')
    return redirect(request.referrer or url_for('loyalty.index'))
