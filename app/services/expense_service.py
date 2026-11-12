from datetime import date
from decimal import Decimal
from sqlalchemy import func
from app.extensions import db
from app.models.expenses import Expense, ExpenseCategory


class ExpenseServiceError(Exception):
    """Custom exception for expense tracking."""
    pass


class ExpenseService:
    @staticmethod
    def record_expense(category_id, title, amount, expense_date=None, payment_method_id=None, receipt_reference=None, notes=None, user_id=None):
        """Records an operational expense entry."""
        category = ExpenseCategory.query.get(category_id)
        if not category:
            raise ExpenseServiceError(f"Expense category ID {category_id} not found.")

        amt = Decimal(str(amount))
        if amt <= Decimal('0.00'):
            raise ExpenseServiceError("Expense amount must be greater than zero.")

        try:
            expense = Expense(
                category_id=category_id,
                title=title.strip(),
                amount=amt,
                expense_date=expense_date or date.today(),
                payment_method_id=payment_method_id,
                receipt_reference=receipt_reference,
                notes=notes,
                approved_by_user_id=user_id,
                created_by=user_id
            )
            db.session.add(expense)
            db.session.commit()
            return expense
        except Exception as e:
            db.session.rollback()
            raise ExpenseServiceError(f"Failed to record expense: {str(e)}")

    @staticmethod
    def get_expense_summary_by_category():
        """Returns aggregated expense amounts grouped by category."""
        results = (
            db.session.query(
                ExpenseCategory.name,
                func.sum(Expense.amount).label('total_amount'),
                func.count(Expense.id).label('expense_count')
            )
            .join(Expense, Expense.category_id == ExpenseCategory.id)
            .group_by(ExpenseCategory.name)
            .all()
        )
        return [{'category': r[0], 'total': Decimal(str(r[1] or 0)), 'count': r[2]} for r in results]

    @staticmethod
    def get_total_expenses(start_date=None, end_date=None):
        """Returns total expenses within an optional date range."""
        query = db.session.query(func.coalesce(func.sum(Expense.amount), Decimal('0.00')))
        if start_date:
            query = query.filter(Expense.expense_date >= start_date)
        if end_date:
            query = query.filter(Expense.expense_date <= end_date)
        return Decimal(str(query.scalar() or '0.00'))
