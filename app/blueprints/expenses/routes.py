from datetime import date
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from app.extensions import db
from app.models.expenses import Expense, ExpenseCategory
from app.models.billing import PaymentMethod
from app.services.expense_service import ExpenseService, ExpenseServiceError
from app.services.audit_service import AuditService
from app.utils.access_control import permission_required
from app.services.status_service import StatusService, StatusServiceError

expenses_bp = Blueprint('expenses', __name__, url_prefix='/expenses')


@expenses_bp.route('/')
@login_required
@permission_required('expenses.manage')
def index():
    category_id = request.args.get('category_id', type=int)
    selected_status = request.args.get('status', '', type=str)
    if selected_status not in ('active', 'deactive'):
        selected_status = ''
    search = request.args.get('q', '', type=str).strip()
    expenses = Expense.query.filter_by(is_deleted=False).order_by(
        Expense.expense_date.desc(), Expense.id.desc()
    ).all()
    categories = ExpenseCategory.query.order_by(ExpenseCategory.name).all()
    payment_methods = PaymentMethod.query.filter_by(status='active').all()

    category_summary = ExpenseService.get_expense_summary_by_category()
    total_expenses = ExpenseService.get_total_expenses()

    return render_template(
        'expenses/index.html',
        expenses=expenses,
        categories=categories,
        payment_methods=payment_methods,
        category_summary=category_summary,
        total_expenses=total_expenses,
        today=date.today(),
        selected_category_id=category_id,
        selected_status=selected_status,
        search=search
    )


@expenses_bp.route('/create', methods=['POST'])
@login_required
def create_expense():
    category_id = request.form.get('category_id', type=int)
    title = request.form.get('title', '')
    amount = Decimal(request.form.get('amount', '0.00'))
    expense_date_str = request.form.get('expense_date')
    payment_method_id = request.form.get('payment_method_id', type=int)
    receipt_ref = request.form.get('receipt_reference', '')
    notes = request.form.get('notes', '')

    expense_date = None
    if expense_date_str:
        try:
            expense_date = date.fromisoformat(expense_date_str)
        except ValueError:
            expense_date = date.today()

    try:
        expense = ExpenseService.record_expense(
            category_id=category_id,
            title=title,
            amount=amount,
            expense_date=expense_date,
            payment_method_id=payment_method_id if payment_method_id else None,
            receipt_reference=receipt_ref,
            notes=notes,
            user_id=current_user.id
        )
        flash(f"Recorded expense '{expense.title}' for ${expense.amount}.", "success")
        AuditService.log('RECORD_EXPENSE', 'Expense', expense.id, f"${expense.amount} ({expense.category.name})", user_id=current_user.id)
    except ExpenseServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for('expenses.index'))


@expenses_bp.route('/delete/<int:expense_id>', methods=['POST'])
@login_required
@permission_required('expenses.delete')
def delete_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, is_deleted=False).first_or_404()
    expense.soft_delete(user_id=current_user.id)
    db.session.commit()
    AuditService.log(
        'DELETE_EXPENSE',
        'Expense',
        expense.id,
        f"Deleted expense '{expense.title}'.",
        user_id=current_user.id
    )
    flash(f"Expense '{expense.title}' deleted.", 'success')
    return redirect(url_for('expenses.index'))


@expenses_bp.route('/api/data')
@login_required
@permission_required('expenses.manage')
def expenses_api():
    """Server-side DataTables JSON feed for expenses."""
    from app.utils.pagination import paginate_query
    from flask import jsonify

    category_id = request.args.get('category_id', type=int)
    status = request.args.get('status', '', type=str)
    query = Expense.query.filter_by(is_deleted=False)
    if category_id:
        query = query.filter(Expense.category_id == category_id)
    if status in ('active', 'deactive'):
        query = query.filter(Expense.status == status)

    def serialize_expense(e):
        return {
            'id': e.id,
            'title': e.title,
            'notes': e.notes,
            'amount': f"${float(e.amount):.2f}",
            'category': e.category.name if e.category else '-',
            'expense_date': e.expense_date.strftime('%b %d, %Y') if e.expense_date else '-',
            'payment_method': e.payment_method.name if e.payment_method else 'Default',
            'receipt_reference': e.receipt_reference or '-',
            'approved_by': e.approved_by_user.full_name if e.approved_by_user else '-',
            'status': e.status,
            'status_toggle': (
                f'<form method="post" action="{url_for("expenses.toggle_status", expense_id=e.id)}">'
                f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">'
                f'<button class="btn btn-sm btn-outline-secondary" type="submit">'
                f'{"Deactivate" if e.status == "active" else "Activate"}</button></form>'
            )
        }

    res = paginate_query(
        base_query=query,
        model=Expense,
        search_fields=['title', 'receipt_reference', 'notes'],
        default_sort=Expense.expense_date.desc(),
        serializer_func=serialize_expense
    )
    return jsonify(res)


@expenses_bp.route('/<int:expense_id>/toggle-status', methods=['POST'])
@login_required
@permission_required('expenses.manage')
def toggle_status(expense_id):
    expense = Expense.query.filter_by(id=expense_id, is_deleted=False).first_or_404()
    try:
        StatusService.toggle(expense, current_user.id)
        flash(f'Expense status changed to {expense.status}.', 'success')
    except StatusServiceError as exc:
        flash(str(exc), 'danger')
    return redirect(request.referrer or url_for('expenses.index'))
