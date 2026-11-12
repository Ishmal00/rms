from app.extensions import db
from app.models.base import BaseModel


class OrderType(BaseModel):
    """Order fulfillment types (Dine-In, Takeaway, Delivery)."""
    __tablename__ = 'order_types'

    name = db.Column(db.String(50), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)

    # Relationships with explicit foreign_keys
    orders = db.relationship(
        'Order',
        back_populates='order_type',
        foreign_keys='Order.order_type_id',
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<OrderType {self.name}>'


class Order(BaseModel):
    """Customer order header managing items, table assignment, and lifecycle."""
    __tablename__ = 'orders'

    order_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    order_type_id = db.Column(
        db.Integer,
        db.ForeignKey('order_types.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    table_id = db.Column(
        db.Integer,
        db.ForeignKey('restaurant_tables.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    customer_id = db.Column(
        db.Integer,
        db.ForeignKey('customers.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    order_status = db.Column(
        db.String(30),
        nullable=False,
        default='pending',
        index=True
    )  # pending, confirmed, preparing, ready, served, completed, cancelled
    total_amount = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    special_notes = db.Column(db.Text, nullable=True)

    # Relationships with explicit foreign_keys
    order_type = db.relationship('OrderType', back_populates='orders', foreign_keys=[order_type_id])
    table = db.relationship('RestaurantTable', foreign_keys=[table_id])
    customer = db.relationship('Customer', back_populates='orders', foreign_keys=[customer_id])
    user = db.relationship('User', foreign_keys=[user_id])

    items = db.relationship(
        'OrderItem',
        back_populates='order',
        foreign_keys='OrderItem.order_id',
        cascade='all, delete-orphan',
        lazy='joined'
    )
    status_history = db.relationship(
        'OrderStatusHistory',
        back_populates='order',
        foreign_keys='OrderStatusHistory.order_id',
        cascade='all, delete-orphan',
        order_by='OrderStatusHistory.created_at.desc()'
    )
    kitchen_ticket = db.relationship(
        'KitchenTicket',
        back_populates='order',
        foreign_keys='KitchenTicket.order_id',
        uselist=False,
        cascade='all, delete-orphan'
    )
    invoice = db.relationship(
        'Invoice',
        back_populates='order',
        foreign_keys='Invoice.order_id',
        uselist=False
    )

    def calculate_total(self):
        """Calculates total amount from child items."""
        total = sum(item.total_price for item in self.items if not item.is_deleted)
        self.total_amount = total
        return total

    def __repr__(self):
        return f'<Order {self.order_number} [{self.order_status}] - ${self.total_amount}>'


class OrderItem(BaseModel):
    """Line items belonging to an order."""
    __tablename__ = 'order_items'

    order_id = db.Column(
        db.Integer,
        db.ForeignKey('orders.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    menu_item_id = db.Column(
        db.Integer,
        db.ForeignKey('menu_items.id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    item_variant_id = db.Column(
        db.Integer,
        db.ForeignKey('item_variants.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    quantity = db.Column(db.Integer, default=1, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    total_price = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    special_instructions = db.Column(db.String(255), nullable=True)
    item_status = db.Column(db.String(30), default='pending', nullable=False)

    # Relationships with explicit foreign_keys
    order = db.relationship('Order', back_populates='items', foreign_keys=[order_id])
    menu_item = db.relationship('MenuItem', foreign_keys=[menu_item_id])
    variant = db.relationship('ItemVariant', foreign_keys=[item_variant_id])

    def calculate_item_total(self):
        self.total_price = self.unit_price * self.quantity
        return self.total_price

    def __repr__(self):
        return f'<OrderItem {self.quantity}x {self.menu_item_id} (${self.total_price})>'


class OrderStatusHistory(BaseModel):
    """Audit log recording every order status transition and actor."""
    __tablename__ = 'order_status_history'

    order_id = db.Column(
        db.Integer,
        db.ForeignKey('orders.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    from_status = db.Column(db.String(30), nullable=True)
    to_status = db.Column(db.String(30), nullable=False)
    changed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    notes = db.Column(db.Text, nullable=True)

    # Relationships with explicit foreign_keys
    order = db.relationship('Order', back_populates='status_history', foreign_keys=[order_id])
    changed_by_user = db.relationship('User', foreign_keys=[changed_by_user_id])

    def __repr__(self):
        return f'<OrderStatusHistory order={self.order_id}: {self.from_status} -> {self.to_status}>'
