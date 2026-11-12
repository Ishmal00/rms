from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel


class RestaurantTable(BaseModel):
    """Physical dining tables and seating zones in the restaurant."""
    __tablename__ = 'restaurant_tables'

    table_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    capacity = db.Column(db.Integer, nullable=False, default=2)
    location_zone = db.Column(db.String(50), nullable=False, default='Indoor', index=True)
    qr_code_token = db.Column(db.String(100), unique=True, nullable=True)
    table_status = db.Column(
        db.String(30),
        nullable=False,
        default='available',
        index=True
    )  # 'available', 'occupied', 'reserved', 'cleaning', 'maintenance'

    # Relationships
    reservations = db.relationship(
        'Reservation',
        back_populates='table',
        foreign_keys='Reservation.table_id',
        lazy='dynamic',
        order_by='Reservation.reservation_time.desc()'
    )

    def __repr__(self):
        return f'<RestaurantTable {self.table_number} ({self.location_zone}, cap={self.capacity})>'


class Reservation(BaseModel):
    """Customer table reservations and booking status."""
    __tablename__ = 'reservations'

    table_id = db.Column(
        db.Integer,
        db.ForeignKey('restaurant_tables.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(30), nullable=False)
    customer_email = db.Column(db.String(120), nullable=True)
    guest_count = db.Column(db.Integer, nullable=False, default=2)
    reservation_time = db.Column(db.DateTime, nullable=False, index=True)
    reservation_status = db.Column(
        db.String(30),
        nullable=False,
        default='pending',
        index=True
    )  # 'pending', 'confirmed', 'seated', 'cancelled', 'completed'
    special_requests = db.Column(db.Text, nullable=True)

    # Relationships
    table = db.relationship('RestaurantTable', back_populates='reservations', foreign_keys=[table_id])

    def __repr__(self):
        return f'<Reservation {self.customer_name} at {self.reservation_time}>'
