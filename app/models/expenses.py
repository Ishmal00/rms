from app.extensions import db
from app.models.base import BaseModel


class ExpenseCategory(BaseModel):
    """Categorization for operational restaurant expenditures."""
    __tablename__ = 'expense_categories'

    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)

    expenses = db.relationship('Expense', back_populates='category', lazy='dynamic')

    def __repr__(self):
        return f"<ExpenseCategory {self.name}>"


class Expense(BaseModel):
    """Operational expenses (Supplies, Maintenance, Rent, Utilities, etc.)."""
    __tablename__ = 'expenses'

    category_id = db.Column(
        db.Integer,
        db.ForeignKey('expense_categories.id', name='fk_expenses_category_id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    title = db.Column(db.String(150), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    expense_date = db.Column(db.Date, nullable=False, index=True)
    payment_method_id = db.Column(
        db.Integer,
        db.ForeignKey('payment_methods.id', name='fk_expenses_payment_method_id', ondelete='SET NULL'),
        nullable=True
    )
    receipt_reference = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    approved_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', name='fk_expenses_approved_by_user_id', ondelete='SET NULL'),
        nullable=True
    )

    category = db.relationship('ExpenseCategory', back_populates='expenses')
    payment_method = db.relationship('PaymentMethod', foreign_keys=[payment_method_id])
    approved_by_user = db.relationship('User', foreign_keys=[approved_by_user_id])

    def __repr__(self):
        return f"<Expense {self.title} - ${self.amount}>"
