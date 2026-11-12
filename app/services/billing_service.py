import uuid
from datetime import datetime
from decimal import Decimal
from app.extensions import db
from app.services.cache_service import cache
from app.models.billing import Tax, Discount, Coupon, Invoice, InvoiceItem, PaymentMethod, Payment
from app.models.orders import OrderStatusHistory
from app.services.notification_service import NotificationService


class BillingError(Exception):
    """Base exception for billing operations."""
    pass


class CouponValidationError(BillingError):
    """Exception raised when a coupon fails validation criteria."""
    pass


class PaymentProcessingError(BillingError):
    """Exception raised when payment processing fails."""
    pass


class BillingService:
    """Business logic for Invoices, Taxes, Discounts, Coupons, and Payments."""

    @staticmethod
    def validate_coupon(code, order_amount):
        """
        Validates coupon existence, active status, date range, max uses,
        and minimum spend.
        Returns: tuple (Coupon, Decimal discount_value)
        Raises: CouponValidationError
        """
        if not code:
            return None, Decimal('0.00')

        clean_code = code.strip().upper()
        coupon = Coupon.query.filter_by(code=clean_code, is_deleted=False).first()
        if not coupon:
            raise CouponValidationError(f"Coupon code '{clean_code}' is invalid or does not exist.")

        is_valid, msg = coupon.is_valid_for_order(order_amount)
        if not is_valid:
            raise CouponValidationError(msg)

        discount_val = Decimal(str(coupon.calculate_discount(order_amount)))
        return coupon, discount_val

    @staticmethod
    def create_or_update_invoice(order, coupon_code=None, discount_id=None, notes=None, user_id=None):
        """
        Generates or recalculates an invoice for an order.
        Computes subtotals, applicable taxes, discounts, and coupons.
        """
        subtotal = Decimal(str(order.total_amount or 0.00))

        # Calculate taxes
        active_taxes = Tax.query.filter_by(status='active', is_deleted=False).all()
        tax_total = Decimal('0.00')
        for tax in active_taxes:
            if not tax.is_inclusive:
                tax_rate = Decimal(str(tax.rate_percentage)) / Decimal('100.00')
                tax_total += (subtotal * tax_rate).quantize(Decimal('0.01'))

        # Calculate discount if present
        discount_amount = Decimal('0.00')
        if discount_id:
            discount = Discount.query.filter_by(id=discount_id, status='active', is_deleted=False).first()
            if discount:
                if discount.discount_type == 'percentage':
                    rate = Decimal(str(discount.rate)) / Decimal('100.00')
                    discount_amount += (subtotal * rate).quantize(Decimal('0.01'))
                else:
                    discount_amount += min(subtotal, Decimal(str(discount.rate)))

        # Validate and apply coupon if present
        coupon = None
        coupon_id = None
        if coupon_code:
            coupon, coupon_discount = BillingService.validate_coupon(coupon_code, subtotal)
            discount_amount += coupon_discount
            coupon_id = coupon.id

        discount_amount = min(subtotal, discount_amount)
        grand_total = max(Decimal('0.00'), subtotal + tax_total - discount_amount)

        # Retrieve or instantiate invoice
        invoice = Invoice.query.filter_by(order_id=order.id).first()
        if not invoice:
            timestamp_str = datetime.utcnow().strftime('%Y%m%d%H%M')
            unique_suffix = uuid.uuid4().hex[:4].upper()
            invoice = Invoice(
                invoice_number=f"INV-{timestamp_str}-{unique_suffix}",
                order_id=order.id,
                customer_id=order.customer_id,
                subtotal=subtotal,
                tax_amount=tax_total,
                discount_amount=discount_amount,
                coupon_id=coupon_id,
                grand_total=grand_total,
                paid_amount=Decimal('0.00'),
                balance_due=grand_total,
                payment_status='unpaid',
                issued_at=datetime.utcnow()
            )
            db.session.add(invoice)
            db.session.flush()
        else:
            invoice.subtotal = subtotal
            invoice.tax_amount = tax_total
            invoice.discount_amount = discount_amount
            invoice.coupon_id = coupon_id
            invoice.grand_total = grand_total
            invoice.customer_id = order.customer_id
            # Rebalance existing paid vs due
            paid = sum(Decimal(str(p.amount)) for p in invoice.payments if p.payment_status == 'completed' and not p.is_deleted)
            invoice.paid_amount = paid
            invoice.balance_due = max(Decimal('0.00'), grand_total - paid)
            if invoice.payment_status != 'void':
                invoice.payment_status = 'paid' if invoice.balance_due <= 0.00 else ('partial' if paid > 0 else 'unpaid')

        # Synchronize invoice items from order items
        for invoice_item in InvoiceItem.query.filter_by(invoice_id=invoice.id).all():
            invoice_item.soft_delete(user_id=user_id)
        for item in order.items:
            if not item.is_deleted:
                desc = item.menu_item.name if item.menu_item else f"Item #{item.menu_item_id}"
                if item.variant:
                    desc += f" ({item.variant.name})"
                inv_item = InvoiceItem(
                    invoice_id=invoice.id,
                    order_item_id=item.id,
                    description=desc,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    subtotal=item.total_price
                )
                db.session.add(inv_item)

        return invoice

    @staticmethod
    def process_payment(invoice_id, payment_method_id, amount, user_id=None, notes=None, simulate_failure=False):
        """
        ATOMIC TRANSACTION:
        1. Validate invoice and payment method
        2. Create payment record
        3. Update invoice paid amount, balance due, and payment status (paid or partial)
        4. If fully paid: release restaurant table and mark order completed
        5. Commits atomically. If any error occurs, rolls back completely.
        """
        try:
            # 1. Validate invoice
            invoice = Invoice.query.filter_by(id=invoice_id, is_deleted=False).first()
            if not invoice:
                raise PaymentProcessingError(f"Invoice #{invoice_id} not found.")

            if invoice.payment_status == 'paid' and invoice.balance_due <= Decimal('0.00'):
                raise PaymentProcessingError("Invoice is already fully settled.")

            if invoice.payment_status == 'void':
                raise PaymentProcessingError("Cannot process payment for a voided invoice.")

            pm = PaymentMethod.query.filter_by(id=payment_method_id, status='active', is_deleted=False).first()
            if not pm:
                raise PaymentProcessingError("Invalid or inactive payment method selected.")

            pay_amount = Decimal(str(amount)).quantize(Decimal('0.01'))
            if pay_amount <= Decimal('0.00'):
                raise PaymentProcessingError("Payment amount must be greater than zero.")

            if pay_amount > (Decimal(str(invoice.balance_due)) + Decimal('0.01')):
                raise PaymentProcessingError(f"Payment amount (${pay_amount}) exceeds balance due (${invoice.balance_due}).")

            # 2. Record payment
            ref = f"PAY-{datetime.utcnow().strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:6].upper()}"
            payment = Payment(
                transaction_reference=ref,
                invoice_id=invoice.id,
                payment_method_id=pm.id,
                amount=pay_amount,
                payment_status='completed',
                payment_date=datetime.utcnow(),
                processed_by_user_id=user_id,
                notes=notes
            )
            db.session.add(payment)
            NotificationService.create_for_all(
                title='Payment received',
                message=(
                    f'Payment of ${pay_amount:.2f} received for '
                    f'invoice {invoice.invoice_number}.'
                ),
                notification_type='payment_received',
                link=f'/billing/invoices/{invoice.id}',
                created_by=user_id
            )

            # 3. Update invoice balance
            new_paid = Decimal(str(invoice.paid_amount)) + pay_amount
            invoice.paid_amount = new_paid
            new_balance = max(Decimal('0.00'), Decimal(str(invoice.grand_total)) - new_paid)
            invoice.balance_due = new_balance

            # If coupon was used, increment usage count upon first payment
            if invoice.coupon and invoice.coupon.usage_count < invoice.coupon.max_uses:
                invoice.coupon.usage_count += 1

            # 4. Check if fully paid
            if new_balance <= Decimal('0.00'):
                invoice.payment_status = 'paid'

                # Complete order and free table
                if invoice.order:
                    order = invoice.order
                    old_status = order.order_status
                    order.order_status = 'completed'

                    # Log to OrderStatusHistory
                    history = OrderStatusHistory(
                        order_id=order.id,
                        from_status=old_status,
                        to_status='completed',
                        changed_by_user_id=user_id,
                        notes=f"Order completed following full settlement via Invoice {invoice.invoice_number}."
                    )
                    db.session.add(history)

                    # Free the table if assigned
                    if order.table:
                        order.table.table_status = 'available'

            else:
                invoice.payment_status = 'partial'

            # Forced failure injection for rollback verification testing
            if simulate_failure:
                raise PaymentProcessingError("Forced test error triggering payment transaction rollback.")

            # --- COMMIT POINT ---
            # All changes (Payment, Invoice status/balances, Order completion, Table release) committed atomically
            db.session.commit()

            # Invalidate dashboard and financial report caches
            cache.delete_pattern("dashboard:*")
            cache.delete_pattern("reports:*")
            return payment

        except Exception as e:
            # --- ROLLBACK POINT ---
            # Reverts payment record, invoice status, table status, and order status
            db.session.rollback()
            raise PaymentProcessingError(str(e))
