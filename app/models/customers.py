from app.extensions import db
from app.models.base import BaseModel


class Customer(BaseModel):
    """Customer profile for dine-in, takeaway, and delivery orders."""
    __tablename__ = 'customers'

    name = db.Column(db.String(100), nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    phone = db.Column(db.String(30), nullable=False, index=True)
    loyalty_points = db.Column(db.Integer, default=0, nullable=False, index=True)
    notes = db.Column(db.Text, nullable=True)

    # Relationships with explicit foreign_keys
    addresses = db.relationship(
        'Address',
        back_populates='customer',
        foreign_keys='Address.customer_id',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )
    orders = db.relationship(
        'Order',
        back_populates='customer',
        foreign_keys='Order.customer_id',
        lazy='dynamic'
    )
    invoices = db.relationship(
        'Invoice',
        back_populates='customer',
        foreign_keys='Invoice.customer_id',
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<Customer {self.name} ({self.phone})>'


class Address(BaseModel):
    """Customer delivery/billing physical address."""
    __tablename__ = 'addresses'

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey('customers.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    address_line1 = db.Column(db.String(200), nullable=False)
    address_line2 = db.Column(db.String(200), nullable=True)
    city = db.Column(db.String(80), nullable=False)
    state = db.Column(db.String(80), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    address_type = db.Column(db.String(30), default='Home', nullable=False)  # Home, Work, Other
    is_default = db.Column(db.Boolean, default=False, nullable=False)

    # Relationships with explicit foreign_keys
    customer = db.relationship('Customer', back_populates='addresses', foreign_keys=[customer_id])

    def __repr__(self):
        return f'<Address {self.address_line1}, {self.city}>'
