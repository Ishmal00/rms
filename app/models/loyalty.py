from app.extensions import db
from app.models.base import BaseModel


class LoyaltyProgram(BaseModel):
    """Membership loyalty tiers with earn and burn rules."""
    __tablename__ = 'loyalty_programs'

    tier_name = db.Column(db.String(50), unique=True, nullable=False)  # Bronze, Silver, Gold, Platinum
    min_spend = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    points_per_dollar = db.Column(db.Numeric(5, 2), default=1.00, nullable=False)
    discount_per_point = db.Column(db.Numeric(6, 4), default=0.0100, nullable=False)  # 100 points = $1.00
    perks_description = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<LoyaltyProgram {self.tier_name} ({self.points_per_dollar} pts/$)>"


class LoyaltyTransaction(BaseModel):
    """Audit ledger of customer loyalty points accrued or burned."""
    __tablename__ = 'loyalty_transactions'

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey('customers.id', name='fk_loyalty_tx_customer_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    order_id = db.Column(
        db.Integer,
        db.ForeignKey('orders.id', name='fk_loyalty_tx_order_id', ondelete='SET NULL'),
        nullable=True
    )
    points = db.Column(db.Integer, nullable=False)  # Positive for earn/adjustment, negative for redeem
    transaction_type = db.Column(db.String(20), nullable=False)  # earn, redeem, adjustment, expire
    balance_after = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.String(255), nullable=True)

    customer = db.relationship('Customer', backref=db.backref('loyalty_history', lazy='dynamic'))
    order = db.relationship('Order')

    def __repr__(self):
        return f"<LoyaltyTransaction cust={self.customer_id} {self.transaction_type} {self.points}pts>"


class Reward(BaseModel):
    """Redeemable catalog rewards and vouchers."""
    __tablename__ = 'rewards'

    title = db.Column(db.String(150), nullable=False)
    points_required = db.Column(db.Integer, nullable=False, index=True)
    reward_type = db.Column(db.String(50), default='discount_voucher', nullable=False)  # discount_voucher, free_item
    reward_value = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    def __repr__(self):
        return f"<Reward {self.title} ({self.points_required} pts)>"
