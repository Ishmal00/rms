from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models.billing import Invoice, PaymentMethod
from app.services.billing_service import BillingService, BillingError
from app.utils.access_control import permission_required

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')


@billing_bp.route('/invoices/<int:invoice_id>')
@login_required
@permission_required('billing.manage')
def invoice_detail(invoice_id):
    """Invoice view and payment terminal supporting split payments."""
    invoice = Invoice.query.filter_by(id=invoice_id, is_deleted=False).first_or_404()
    payment_methods = PaymentMethod.query.filter_by(status='active', is_deleted=False).all()

    return render_template(
        'billing/invoice.html',
        invoice=invoice,
        payment_methods=payment_methods
    )


@billing_bp.route('/invoices/<int:invoice_id>/pay', methods=['POST'])
@login_required
@permission_required('billing.manage')
def pay_invoice(invoice_id):
    """Processes payment atomically via BillingService."""
    payment_method_id = request.form.get('payment_method_id', type=int)
    amount = request.form.get('amount', type=float)
    notes = request.form.get('notes')

    try:
        payment = BillingService.process_payment(
            invoice_id=invoice_id,
            payment_method_id=payment_method_id,
            amount=amount,
            user_id=current_user.id,
            notes=notes
        )
        flash(f"Payment of ${payment.amount:.2f} processed successfully! Ref: {payment.transaction_reference}", 'success')
    except BillingError as e:
        flash(f"Payment failed: {str(e)}", 'danger')

    return redirect(url_for('billing.invoice_detail', invoice_id=invoice_id))


@billing_bp.route('/invoices/<int:invoice_id>/coupon', methods=['POST'])
@login_required
@permission_required('billing.manage')
def apply_coupon(invoice_id):
    """Applies a promotional coupon to an invoice."""
    coupon_code = request.form.get('coupon_code', '').strip()
    invoice = Invoice.query.filter_by(id=invoice_id, is_deleted=False).first_or_404()

    if not invoice.order:
        flash("Invoice has no associated order.", 'danger')
        return redirect(url_for('billing.invoice_detail', invoice_id=invoice_id))

    try:
        BillingService.create_or_update_invoice(
            order=invoice.order,
            coupon_code=coupon_code,
            user_id=current_user.id
        )
        from app.extensions import db
        db.session.commit()
        flash(f"Coupon '{coupon_code}' applied successfully!", 'success')
    except BillingError as e:
        flash(f"Could not apply coupon: {str(e)}", 'danger')

    return redirect(url_for('billing.invoice_detail', invoice_id=invoice_id))


@billing_bp.route('/invoices/<int:invoice_id>/print')
@login_required
@permission_required('billing.manage')
def print_invoice(invoice_id):
    """Print-friendly receipt view."""
    invoice = Invoice.query.filter_by(id=invoice_id, is_deleted=False).first_or_404()
    return render_template('billing/print_invoice.html', invoice=invoice)
