from app.extensions import db
from app.models.base import BaseModel


class CustomerFeedback(BaseModel):
    """Customer ratings and satisfaction reviews."""
    __tablename__ = 'customer_feedbacks'

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey('customers.id', name='fk_feedbacks_customer_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    order_id = db.Column(
        db.Integer,
        db.ForeignKey('orders.id', name='fk_feedbacks_order_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    food_rating = db.Column(db.Integer, nullable=False)  # 1-5
    service_rating = db.Column(db.Integer, nullable=False)  # 1-5
    ambience_rating = db.Column(db.Integer, nullable=False)  # 1-5
    overall_rating = db.Column(db.Numeric(3, 2), nullable=False)  # Average of ratings
    comments = db.Column(db.Text, nullable=True)
    response_notes = db.Column(db.Text, nullable=True)
    is_published = db.Column(db.Boolean, default=True, nullable=False, index=True)

    customer = db.relationship('Customer', foreign_keys=[customer_id])
    order = db.relationship('Order', foreign_keys=[order_id])

    def __repr__(self):
        return f"<CustomerFeedback id={self.id} rating={self.overall_rating}>"
