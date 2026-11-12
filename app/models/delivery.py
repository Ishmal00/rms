from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel


class DeliveryAgent(BaseModel):
    """Delivery drivers and courier personnel."""
    __tablename__ = 'delivery_agents'

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', name='fk_delivery_agents_user_id', ondelete='SET NULL'),
        nullable=True
    )
    employee_id = db.Column(
        db.Integer,
        db.ForeignKey('employees.id', name='fk_delivery_agents_employee_id', ondelete='SET NULL'),
        nullable=True
    )
    name = db.Column(db.String(100), nullable=False)
    vehicle_type = db.Column(db.String(50), default='bike', nullable=False)  # bike, scooter, car, van
    license_plate = db.Column(db.String(50), nullable=True)
    phone = db.Column(db.String(30), nullable=False, index=True)
    is_available = db.Column(db.Boolean, default=True, nullable=False, index=True)

    user = db.relationship('User', foreign_keys=[user_id])
    employee = db.relationship('Employee', foreign_keys=[employee_id])
    deliveries = db.relationship('Delivery', back_populates='delivery_agent', lazy='dynamic')

    def __repr__(self):
        return f"<DeliveryAgent {self.name} ({self.vehicle_type}) available={self.is_available}>"


class Delivery(BaseModel):
    """Delivery dispatch and fulfillment records tied to orders."""
    __tablename__ = 'deliveries'

    order_id = db.Column(
        db.Integer,
        db.ForeignKey('orders.id', name='fk_deliveries_order_id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True
    )
    delivery_agent_id = db.Column(
        db.Integer,
        db.ForeignKey('delivery_agents.id', name='fk_deliveries_agent_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    address_id = db.Column(
        db.Integer,
        db.ForeignKey('addresses.id', name='fk_deliveries_address_id', ondelete='RESTRICT'),
        nullable=False
    )
    delivery_fee = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    delivery_status = db.Column(
        db.String(30),
        default='pending',
        nullable=False,
        index=True
    )  # pending, assigned, picked_up, in_transit, delivered, failed
    assigned_at = db.Column(db.DateTime, nullable=True)
    picked_up_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    delivery_notes = db.Column(db.Text, nullable=True)

    order = db.relationship('Order', backref=db.backref('delivery_record', uselist=False))
    delivery_agent = db.relationship('DeliveryAgent', back_populates='deliveries')
    address = db.relationship('Address')
    tracking_events = db.relationship('DeliveryTracking', back_populates='delivery', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Delivery order={self.order_id} status={self.delivery_status}>"


class DeliveryTracking(BaseModel):
    """Route progress checkpoints and status events."""
    __tablename__ = 'delivery_tracking'

    delivery_id = db.Column(
        db.Integer,
        db.ForeignKey('deliveries.id', name='fk_delivery_tracking_delivery_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    status = db.Column(db.String(30), nullable=False)
    latitude = db.Column(db.Numeric(9, 6), nullable=True)
    longitude = db.Column(db.Numeric(9, 6), nullable=True)
    checkpoint_notes = db.Column(db.String(255), nullable=True)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    delivery = db.relationship('Delivery', back_populates='tracking_events')

    def __repr__(self):
        return f"<DeliveryTracking delivery={self.delivery_id} status={self.status} at={self.recorded_at}>"
