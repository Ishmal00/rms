from datetime import datetime
from app.extensions import db
from app.models.base import BaseModel


class KitchenTicket(BaseModel):
    """Kitchen Order Ticket (KOT) displayed on the Kitchen Display System (KDS)."""
    __tablename__ = 'kitchen_tickets'

    ticket_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey('orders.id', ondelete='CASCADE'),
        unique=True,
        nullable=False,
        index=True
    )
    kitchen_status = db.Column(
        db.String(30),
        nullable=False,
        default='pending',
        index=True
    )  # pending, preparing, ready, served, cancelled
    prep_started_at = db.Column(db.DateTime, nullable=True)
    ready_at = db.Column(db.DateTime, nullable=True)
    served_at = db.Column(db.DateTime, nullable=True)
    priority = db.Column(db.String(20), default='normal', nullable=False)  # low, normal, high, urgent
    notes = db.Column(db.Text, nullable=True)

    # Relationships with explicit foreign_keys
    order = db.relationship('Order', back_populates='kitchen_ticket', foreign_keys=[order_id])

    def mark_preparing(self):
        self.kitchen_status = 'preparing'
        self.prep_started_at = datetime.utcnow()

    def mark_ready(self):
        self.kitchen_status = 'ready'
        self.ready_at = datetime.utcnow()

    def mark_served(self):
        self.kitchen_status = 'served'
        self.served_at = datetime.utcnow()

    def __repr__(self):
        return f'<KitchenTicket {self.ticket_number} [{self.kitchen_status}]>'
