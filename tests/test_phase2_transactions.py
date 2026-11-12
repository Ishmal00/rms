import uuid
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models.orders import Order, OrderItem, OrderType, OrderStatusHistory
from app.models.kitchen import KitchenTicket
from app.models.tables import RestaurantTable
from app.models.menu import MenuItem
from app.models.inventory import InventoryItem, StockMovement
from app.models.billing import Invoice, InvoiceItem, PaymentMethod, Payment, Coupon
from app.models.auth import User
from app.services.order_service import OrderService, OrderPlacementError, OrderCancellationError
from app.services.billing_service import BillingService, PaymentProcessingError, CouponValidationError
from sqlalchemy.engine import make_url


def create_test_app():
    database_url = TestingConfig.SQLALCHEMY_DATABASE_URI
    if not database_url:
        raise RuntimeError(
            "Tests aborted: set TEST_DATABASE_URL to the test database "
            "(its database name must contain 'test')."
        )
    database_name = make_url(database_url).database or ''
    if 'test' not in database_name.lower():
        raise RuntimeError(
            "Tests aborted: TEST_DATABASE_URL must target a database whose "
            f"name contains 'test'; got {database_name!r}."
        )
    return create_app('testing')


@pytest.fixture(scope='module')
def app():
    """Create and configure a Flask application context for pytest."""
    application = create_test_app()
    with application.app_context():
        import app.models
        from app.seeds.seed_data import seed_database

        db.drop_all()
        db.create_all()
        seed_database()
        yield application


@pytest.fixture(autouse=True)
def run_around_tests(app):
    """Clean execution context for each test."""
    yield


def test_01_place_order_atomic_success(app):
    """
    Test 1: Place Order Atomic Transaction
    Verifies that Order, OrderItems, KitchenTicket, Table occupancy,
    Stock deduction, and Draft Invoice are created together atomically.
    """
    # Arrange
    admin = User.query.filter_by(username='admin').first()
    table = RestaurantTable.query.filter_by(table_number='T-01').first()
    table.table_status = 'available'
    db.session.commit()

    bruschetta = MenuItem.query.filter_by(slug='bruschetta').first()
    inv_item = InventoryItem.query.first()
    initial_stock = Decimal(str(inv_item.current_stock))

    # Act
    order = OrderService.place_order(
        order_type_slug='dine-in',
        items_data=[{'menu_item_id': bruschetta.id, 'quantity': 2}],
        table_id=table.id,
        user_id=admin.id,
        special_notes='Test order'
    )

    # Assert
    assert order is not None
    assert order.order_status == 'pending'
    assert order.items[0].quantity == 2

    # Check Table Status changed to occupied
    db.session.refresh(table)
    assert table.table_status == 'occupied'

    # Check Kitchen Ticket created
    assert order.kitchen_ticket is not None
    assert order.kitchen_ticket.kitchen_status == 'pending'

    # Check Inventory Deduction
    db.session.refresh(inv_item)
    assert Decimal(str(inv_item.current_stock)) < initial_stock

    # Check Stock Movement OUT record
    movement = StockMovement.query.filter_by(reference_no=order.order_number, movement_type='OUT').first()
    assert movement is not None
    assert Decimal(str(movement.quantity)) == Decimal('2.00')

    # Check Draft Invoice created
    assert order.invoice is not None
    assert order.invoice.payment_status == 'unpaid'
    assert Decimal(str(order.invoice.grand_total)) > Decimal('0.00')

    # Check OrderStatusHistory logged
    history = OrderStatusHistory.query.filter_by(order_id=order.id).first()
    assert history is not None
    assert history.to_status == 'pending'


def test_02_place_order_forced_failure_rollback(app):
    """
    Test 2: Place Order Forced Failure & Rollback
    Simulates a failure during order placement and proves that
    the database state (table status, stock, order count) is completely untouched.
    """
    # Arrange
    admin = User.query.filter_by(username='admin').first()
    table = RestaurantTable.query.filter_by(table_number='T-03').first()
    table.table_status = 'available'
    db.session.commit()

    inv_item = InventoryItem.query.first()
    baseline_stock = Decimal(str(inv_item.current_stock))
    baseline_order_count = Order.query.count()

    bruschetta = MenuItem.query.filter_by(slug='bruschetta').first()

    # Act & Assert
    with pytest.raises(OrderPlacementError):
        OrderService.place_order(
            order_type_slug='dine-in',
            items_data=[{'menu_item_id': bruschetta.id, 'quantity': 3}],
            table_id=table.id,
            user_id=admin.id,
            simulate_failure=True  # Injects forced failure before commit
        )

    # Verify Rollback: Order count did NOT increase
    assert Order.query.count() == baseline_order_count

    # Table status is STILL 'available'
    db.session.refresh(table)
    assert table.table_status == 'available'

    # Inventory stock is EXACTLY untouched
    db.session.refresh(inv_item)
    assert Decimal(str(inv_item.current_stock)) == baseline_stock


def test_03_place_order_insufficient_stock_rolls_back(app):
    admin = User.query.filter_by(username='admin').first()
    table = RestaurantTable.query.filter_by(table_number='T-03').first()
    table.table_status = 'available'
    inv_item = InventoryItem.query.filter_by(name='Ribeye Cut Beef').first()
    steak = MenuItem.query.filter_by(slug='prime-ribeye-steak').first()

    original_stock = Decimal(str(inv_item.current_stock))
    inv_item.current_stock = Decimal('0.50')
    db.session.commit()

    baseline_order_count = Order.query.count()
    baseline_movement_count = StockMovement.query.count()

    with pytest.raises(OrderPlacementError, match='Insufficient stock for Ribeye Cut Beef') as exc_info:
        OrderService.place_order(
            order_type_slug='dine-in',
            items_data=[{'menu_item_id': steak.id, 'quantity': 1}],
            table_id=table.id,
            user_id=admin.id
        )

    assert 'requested 1 kg, available 0.50 kg' in str(exc_info.value)
    assert Order.query.count() == baseline_order_count
    assert StockMovement.query.count() == baseline_movement_count
    db.session.refresh(table)
    assert table.table_status == 'available'
    db.session.refresh(inv_item)
    assert Decimal(str(inv_item.current_stock)) == Decimal('0.50')

    inv_item.current_stock = original_stock
    db.session.commit()


def test_03_payment_processing_partial_and_full(app):
    """
    Test 3: Process Payment Atomic Transaction
    Tests split payments: partial payment leaves table occupied;
    final payment settles invoice, completes order, and frees table.
    """
    # Arrange: create an order with table
    admin = User.query.filter_by(username='admin').first()
    table = RestaurantTable.query.filter_by(table_number='T-04').first()
    table.table_status = 'available'
    db.session.commit()

    bruschetta = MenuItem.query.filter_by(slug='bruschetta').first()
    order = OrderService.place_order(
        order_type_slug='dine-in',
        items_data=[{'menu_item_id': bruschetta.id, 'quantity': 1}],
        table_id=table.id,
        user_id=admin.id
    )
    invoice = order.invoice
    grand_total = Decimal(str(invoice.grand_total))
    assert grand_total > Decimal('0.00')

    pm_cash = PaymentMethod.query.filter_by(slug='cash').first()
    pm_card = PaymentMethod.query.filter_by(slug='credit_card').first()

    # Act 1: Partial payment of $5.00
    partial_amount = Decimal('5.00')
    BillingService.process_payment(
        invoice_id=invoice.id,
        payment_method_id=pm_cash.id,
        amount=partial_amount,
        user_id=admin.id
    )

    db.session.refresh(invoice)
    db.session.refresh(order)
    db.session.refresh(table)

    # Assert 1: Status is partial, table is still occupied, order active
    assert invoice.payment_status == 'partial'
    assert Decimal(str(invoice.paid_amount)) == partial_amount
    assert Decimal(str(invoice.balance_due)) == grand_total - partial_amount
    assert table.table_status == 'occupied'
    assert order.order_status == 'pending'

    # Act 2: Settle remaining balance
    remaining_balance = Decimal(str(invoice.balance_due))
    BillingService.process_payment(
        invoice_id=invoice.id,
        payment_method_id=pm_card.id,
        amount=remaining_balance,
        user_id=admin.id
    )

    db.session.refresh(invoice)
    db.session.refresh(order)
    db.session.refresh(table)

    # Assert 2: Invoice is paid, Order is completed, Table is freed!
    assert invoice.payment_status == 'paid'
    assert Decimal(str(invoice.balance_due)) == Decimal('0.00')
    assert order.order_status == 'completed'
    assert table.table_status == 'available'

    # History entry created
    history = OrderStatusHistory.query.filter_by(order_id=order.id, to_status='completed').first()
    assert history is not None


def test_04_payment_processing_forced_failure_rollback(app):
    """
    Test 4: Process Payment Forced Failure & Rollback
    Simulates a failure during payment processing and verifies
    that no payment record is persisted and invoice status is unchanged.
    """
    admin = User.query.filter_by(username='admin').first()
    table = RestaurantTable.query.filter_by(table_number='BAR-01').first()
    table.table_status = 'available'
    db.session.commit()

    bruschetta = MenuItem.query.filter_by(slug='bruschetta').first()
    order = OrderService.place_order(
        order_type_slug='dine-in',
        items_data=[{'menu_item_id': bruschetta.id, 'quantity': 1}],
        table_id=table.id,
        user_id=admin.id
    )
    invoice = order.invoice
    initial_paid = Decimal(str(invoice.paid_amount))
    initial_balance = Decimal(str(invoice.balance_due))
    initial_payment_count = Payment.query.count()

    pm_cash = PaymentMethod.query.filter_by(slug='cash').first()

    # Act & Assert
    with pytest.raises(PaymentProcessingError):
        BillingService.process_payment(
            invoice_id=invoice.id,
            payment_method_id=pm_cash.id,
            amount=Decimal('5.00'),
            user_id=admin.id,
            simulate_failure=True  # Injects forced failure
        )

    # Verify Rollback: Payment count unchanged
    assert Payment.query.count() == initial_payment_count

    # Invoice balance and status untouched
    db.session.refresh(invoice)
    assert Decimal(str(invoice.paid_amount)) == initial_paid
    assert Decimal(str(invoice.balance_due)) == initial_balance
    assert invoice.payment_status == 'unpaid'


def test_05_cancel_order_atomic_success(app):
    """
    Test 5: Cancel Order Atomic Transaction
    Cancelling an order restores inventory via reverse StockMovements,
    frees the table, voids the invoice, and logs the cancellation.
    """
    # Arrange
    admin = User.query.filter_by(username='admin').first()
    table = RestaurantTable.query.filter_by(table_number='VIP-01').first()
    table.table_status = 'available'
    db.session.commit()

    bruschetta = MenuItem.query.filter_by(slug='bruschetta').first()
    inv_item = InventoryItem.query.first()

    order = OrderService.place_order(
        order_type_slug='dine-in',
        items_data=[{'menu_item_id': bruschetta.id, 'quantity': 2}],
        table_id=table.id,
        user_id=admin.id
    )
    db.session.refresh(inv_item)
    stock_after_order = Decimal(str(inv_item.current_stock))

    # Act: Cancel the order
    cancelled_order = OrderService.cancel_order(
        order_id=order.id,
        user_id=admin.id,
        reason='Customer changed mind'
    )

    # Assert
    assert cancelled_order.order_status == 'cancelled'

    # Kitchen ticket cancelled
    assert cancelled_order.kitchen_ticket.kitchen_status == 'cancelled'

    # Table freed
    db.session.refresh(table)
    assert table.table_status == 'available'

    # Inventory restored
    db.session.refresh(inv_item)
    assert Decimal(str(inv_item.current_stock)) == stock_after_order + Decimal('2.00')

    # Reverse movement recorded
    rev_movement = StockMovement.query.filter_by(
        reference_no=f"REV-{order.order_number}",
        movement_type='IN'
    ).first()
    assert rev_movement is not None
    assert Decimal(str(rev_movement.quantity)) == Decimal('2.00')

    # Invoice voided
    assert cancelled_order.invoice.payment_status == 'void'


def test_06_cancel_order_forced_failure_rollback(app):
    """
    Test 6: Cancel Order Forced Failure & Rollback
    Simulates a failure during cancellation and proves that
    order status, table status, and inventory remain un-cancelled.
    """
    admin = User.query.filter_by(username='admin').first()
    table = RestaurantTable.query.filter_by(table_number='BAR-02').first()
    table.table_status = 'available'
    db.session.commit()

    bruschetta = MenuItem.query.filter_by(slug='bruschetta').first()
    order = OrderService.place_order(
        order_type_slug='dine-in',
        items_data=[{'menu_item_id': bruschetta.id, 'quantity': 1}],
        table_id=table.id,
        user_id=admin.id
    )

    inv_item = InventoryItem.query.first()
    stock_before_cancel = Decimal(str(inv_item.current_stock))

    # Act & Assert
    with pytest.raises(OrderCancellationError):
        OrderService.cancel_order(
            order_id=order.id,
            user_id=admin.id,
            simulate_failure=True  # Injects forced failure
        )

    # Verify Rollback: Order is still 'pending'
    db.session.refresh(order)
    assert order.order_status == 'pending'

    # Table is still 'occupied'
    db.session.refresh(table)
    assert table.table_status == 'occupied'

    # Stock was NOT restored prematurely
    db.session.refresh(inv_item)
    assert Decimal(str(inv_item.current_stock)) == stock_before_cancel


def test_07_coupon_validation(app):
    """
    Test 7: Coupon Validation Logic
    Tests expiry, minimum spend threshold, and discount calculations.
    """
    # 1. Valid coupon WELCOME10 (10% off min $20)
    coupon, discount = BillingService.validate_coupon('WELCOME10', Decimal('50.00'))
    assert coupon is not None
    assert coupon.code == 'WELCOME10'
    assert discount == Decimal('5.00')

    # 2. Coupon with order below minimum spend threshold
    with pytest.raises(CouponValidationError) as exc_info:
        BillingService.validate_coupon('WELCOME10', Decimal('15.00'))
    assert "Minimum order amount" in str(exc_info.value)


def test_08_invoice_item_sync_soft_deletes_previous_items(app):
    admin = User.query.filter_by(username='admin').first()
    bruschetta = MenuItem.query.filter_by(slug='bruschetta').first()
    order = OrderService.place_order(
        order_type_slug='takeaway',
        items_data=[{'menu_item_id': bruschetta.id, 'quantity': 1}],
        user_id=admin.id
    )
    previous_items = InvoiceItem.query.filter_by(invoice_id=order.invoice.id).all()
    assert previous_items
    previous_item_ids = [item.id for item in previous_items]

    BillingService.create_or_update_invoice(order, user_id=admin.id)

    deleted_items = InvoiceItem.query_with_deleted().filter(
        InvoiceItem.id.in_(previous_item_ids)
    ).all()
    assert all(item.is_deleted for item in deleted_items)
    assert all(item.deleted_by == admin.id for item in deleted_items)
    assert all(item.deleted_at is not None for item in deleted_items)
    assert InvoiceItem.query.filter_by(invoice_id=order.invoice.id).count() > 0

    # 3. Non-existent coupon code
    with pytest.raises(CouponValidationError) as exc_info:
        BillingService.validate_coupon('INVALIDCODE999', Decimal('50.00'))
    assert "invalid or does not exist" in str(exc_info.value)

    # 4. Expired coupon test
    expired_code = f"EXP_{uuid.uuid4().hex[:6].upper()}"
    expired_coupon = Coupon(
        code=expired_code,
        discount_type='percentage',
        discount_value=Decimal('50.00'),
        min_order_amount=Decimal('0.00'),
        max_uses=10,
        valid_from=datetime.utcnow() - timedelta(days=10),
        valid_until=datetime.utcnow() - timedelta(days=1)
    )
    db.session.add(expired_coupon)
    db.session.commit()

    with pytest.raises(CouponValidationError) as exc_info:
        BillingService.validate_coupon(expired_code, Decimal('50.00'))
    assert "expired" in str(exc_info.value).lower()
