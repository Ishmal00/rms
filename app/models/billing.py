from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel


class Tax(BaseModel):
    """Applicable government and service taxes."""
    __tablename__ = 'taxes'

    name = db.Column(db.String(50), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    rate_percentage = db.Column(db.Numeric(5, 2), nullable=False)
    is_inclusive = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f'<Tax {self.name} ({self.rate_percentage}%)>'


class Discount(BaseModel):
    """Pre-set discount rules (Happy Hour, Senior Citizen, Staff)."""
    __tablename__ = 'discounts'

    name = db.Column(db.String(80), nullable=False)
    discount_type = db.Column(db.String(20), default='percentage', nullable=False)  # percentage, fixed_amount
    rate = db.Column(db.Numeric(10, 2), nullable=False)

    def __repr__(self):
        return f'<Discount {self.name} ({self.rate})>'


class Coupon(BaseModel):
    """Promotional coupon codes with validity, usage limits, and minimum spend."""
    __tablename__ = 'coupons'

    code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    discount_type = db.Column(db.String(20), default='percentage', nullable=False)  # percentage, fixed_amount
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)
    min_order_amount = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    max_uses = db.Column(db.Integer, default=100, nullable=False)
    usage_count = db.Column(db.Integer, default=0, nullable=False)
    valid_from = db.Column(db.DateTime, nullable=False)
    valid_until = db.Column(db.DateTime, nullable=False)

    # Relationships with explicit foreign_keys
    invoices = db.relationship('Invoice', back_populates='coupon', foreign_keys='Invoice.coupon_id')

    def is_valid_for_order(self, order_amount=0.0):
        """Validates coupon constraints."""
        now = datetime.utcnow()
        if self.status != 'active' or self.is_deleted:
            return False, "Coupon is not active."
        if now < self.valid_from or now > self.valid_until:
            return False, "Coupon has expired or is not yet active."
        if self.usage_count >= self.max_uses:
            return False, "Coupon usage limit has been reached."
        if float(order_amount) < float(self.min_order_amount):
            return False, f"Minimum order amount of ${float(self.min_order_amount):.2f} required."
        return True, "Coupon is valid."

    def calculate_discount(self, order_amount):
        """Calculates discount value."""
        if self.discount_type == 'percentage':
            return round((float(order_amount) * float(self.discount_value)) / 100.0, 2)
        return min(float(order_amount), float(self.discount_value))

    def __repr__(self):
        return f'<Coupon {self.code} ({self.discount_value})>'


class Invoice(BaseModel):
    """Customer invoice generated for an order, supporting split payments."""
    __tablename__ = 'invoices'

    invoice_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey('orders.id', ondelete='RESTRICT'),
        unique=True,
        nullable=False,
        index=True
    )
    customer_id = db.Column(
        db.Integer,
        db.ForeignKey('customers.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    subtotal = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    tax_amount = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    discount_amount = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    coupon_id = db.Column(
        db.Integer,
        db.ForeignKey('coupons.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    grand_total = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    paid_amount = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    balance_due = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    payment_status = db.Column(
        db.String(20),
        default='unpaid',
        nullable=False,
        index=True
    )  # unpaid, partial, paid, void
    issued_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships with explicit foreign_keys
    order = db.relationship('Order', back_populates='invoice', foreign_keys=[order_id])
    customer = db.relationship('Customer', back_populates='invoices', foreign_keys=[customer_id])
    coupon = db.relationship('Coupon', back_populates='invoices', foreign_keys=[coupon_id])

    items = db.relationship(
        'InvoiceItem',
        back_populates='invoice',
        foreign_keys='InvoiceItem.invoice_id',
        cascade='all, delete-orphan',
        lazy='joined'
    )
    payments = db.relationship(
        'Payment',
        back_populates='invoice',
        foreign_keys='Payment.invoice_id',
        cascade='all, delete-orphan',
        order_by='Payment.payment_date.asc()'
    )

    def recalculate_balances(self):
        """Recalculates grand total and balance due."""
        self.grand_total = max(0.00, float(self.subtotal) + float(self.tax_amount) - float(self.discount_amount))
        total_paid = sum(float(p.amount) for p in self.payments if p.payment_status == 'completed' and not p.is_deleted)
        self.paid_amount = total_paid
        self.balance_due = max(0.00, float(self.grand_total) - float(self.paid_amount))

        if self.payment_status != 'void':
            if self.balance_due <= 0.00 and float(self.grand_total) > 0:
                self.payment_status = 'paid'
            elif float(self.paid_amount) > 0:
                self.payment_status = 'partial'
            else:
                self.payment_status = 'unpaid'

    def __repr__(self):
        return f'<Invoice {self.invoice_number} [{self.payment_status}] Total: ${self.grand_total} Due: ${self.balance_due}>'


class InvoiceItem(BaseModel):
    """Line items on an invoice."""
    __tablename__ = 'invoice_items'

    invoice_id = db.Column(
        db.Integer,
        db.ForeignKey('invoices.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    order_item_id = db.Column(
        db.Integer,
        db.ForeignKey('order_items.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)

    # Relationships with explicit foreign_keys
    invoice = db.relationship('Invoice', back_populates='items', foreign_keys=[invoice_id])
    order_item = db.relationship('OrderItem', foreign_keys=[order_item_id])

    def __repr__(self):
        return f'<InvoiceItem {self.description} x{self.quantity} (${self.subtotal})>'


class PaymentMethod(BaseModel):
    """Available payment methods (Cash, Credit Card, Mobile Wallet, etc.)."""
    __tablename__ = 'payment_methods'

    name = db.Column(db.String(50), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    is_cash = db.Column(db.Boolean, default=False, nullable=False)
    is_digital = db.Column(db.Boolean, default=True, nullable=False)

    # Relationships with explicit foreign_keys
    payments = db.relationship(
        'Payment',
        back_populates='payment_method',
        foreign_keys='Payment.payment_method_id',
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<PaymentMethod {self.name}>'


class Payment(BaseModel):
    """Payment transaction records supporting partial/split settlements."""
    __tablename__ = 'payments'

    transaction_reference = db.Column(db.String(64), unique=True, nullable=False, index=True)
    invoice_id = db.Column(
        db.Integer,
        db.ForeignKey('invoices.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    payment_method_id = db.Column(
        db.Integer,
        db.ForeignKey('payment_methods.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_status = db.Column(
        db.String(20),
        default='completed',
        nullable=False,
        index=True
    )  # completed, failed, refunded, void
    payment_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    processed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    notes = db.Column(db.Text, nullable=True)

    # Relationships with explicit foreign_keys
    invoice = db.relationship('Invoice', back_populates='payments', foreign_keys=[invoice_id])
    payment_method = db.relationship('PaymentMethod', back_populates='payments', foreign_keys=[payment_method_id])
    processed_by_user = db.relationship('User', foreign_keys=[processed_by_user_id])

    def __repr__(self):
        return f'<Payment {self.transaction_reference} - ${self.amount} ({self.payment_status})>'
