from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.customers import Customer
from app.models.loyalty import LoyaltyProgram, LoyaltyTransaction, Reward
from app.services.loyalty_service import LoyaltyService, LoyaltyServiceError
from app.services.audit_service import AuditService

loyalty_bp = Blueprint('loyalty', __name__, url_prefix='/loyalty')


@loyalty_bp.route('/')
@login_required
def index():
    tiers = LoyaltyProgram.query.order_by(LoyaltyProgram.min_spend.asc()).all()
    rewards = Reward.query.filter_by(is_active=True).order_by(Reward.points_required.asc()).all()
    customers = Customer.query.order_by(Customer.loyalty_points.desc()).all()
    recent_txs = LoyaltyTransaction.query.order_by(LoyaltyTransaction.created_at.desc()).limit(20).all()

    return render_template(
        'loyalty/index.html',
        tiers=tiers,
        rewards=rewards,
        customers=customers,
        recent_txs=recent_txs
    )


@loyalty_bp.route('/redeem-reward', methods=['POST'])
@login_required
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
