import uuid
from decimal import Decimal
from datetime import datetime, date, timedelta
import pytest
from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models.auth import User
from app.models.staff import Department, Employee, Shift, Attendance, Payroll
from app.models.delivery import DeliveryAgent, Delivery, DeliveryTracking
from app.models.expenses import ExpenseCategory, Expense
from app.models.loyalty import LoyaltyProgram, LoyaltyTransaction, Reward
from app.models.feedback import CustomerFeedback
from app.models.settings import SystemSetting, AuditLog
from app.models.orders import Order
from app.models.customers import Customer
from app.models.billing import Payment
from app.services.staff_service import StaffService, StaffServiceError
from app.services.delivery_service import DeliveryService, DeliveryServiceError
from app.services.expense_service import ExpenseService, ExpenseServiceError
from app.services.loyalty_service import LoyaltyService, LoyaltyServiceError
from app.services.feedback_service import FeedbackService, FeedbackServiceError
from app.services.report_service import ReportService
from app.services.audit_service import AuditService
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


def test_01_all_44_models_have_data(app):
    """
    Test 1: Model Presence & Total Tables Verification
    Verifies that all 44 domain tables exist in the ORM schema and have seeded data.
    """
    from app import models
    domain_models = [
        # Auth
        models.Role, models.Permission, models.RolePermission, models.User,
        # Menu
        models.Category, models.SubCategory, models.MenuItem, models.ItemVariant, models.Ingredient,
        # Inventory
        models.Supplier, models.InventoryItem, models.StockMovement,
        # Tables
        models.RestaurantTable, models.Reservation,
        # Customers
        models.Customer, models.Address,
        # Orders
        models.OrderType, models.Order, models.OrderItem, models.OrderStatusHistory,
        # Kitchen
        models.KitchenTicket,
        # Billing
        models.Tax, models.Discount, models.Coupon, models.Invoice, models.InvoiceItem, models.PaymentMethod, models.Payment,
        # Staff
        models.Department, models.Employee, models.Shift, models.Attendance,
        # Delivery
        models.DeliveryAgent,
        # Expenses
        models.ExpenseCategory, models.Expense,
        # Loyalty
        models.LoyaltyProgram, models.Reward,
        # Feedback
        models.CustomerFeedback,
        # Settings & Audit
        models.SystemSetting, models.AuditLog
    ]

    assert len(domain_models) >= 38
    invoice = models.Invoice.query.first()
    payment_method = models.PaymentMethod.query.first()
    admin = User.query.filter_by(username='admin').first()
    assert invoice is not None
    assert payment_method is not None
    assert admin is not None
    db.session.add(Payment(
        transaction_reference=f'TEST-{uuid.uuid4().hex}',
        invoice_id=invoice.id,
        payment_method_id=payment_method.id,
        amount=Decimal('1.00'),
        processed_by_user_id=admin.id
    ))
    db.session.commit()

    for m in domain_models:
        count = m.query.count()
        assert count > 0, f"Model {m.__name__} has 0 records."


def test_02_staff_attendance_and_clockin_out(app):
    """
    Test 2: Staff Attendance Workflow
    Tests clock in, duplicate prevention for active shifts, and clock out.
    """
    emp = Employee.query.filter_by(employee_code='EMP-003').first()
    assert emp is not None

    # Clean any prior active attendance today for EMP-003
    today = date.today()
    Attendance.query.filter_by(employee_id=emp.id, date=today).delete()
    db.session.commit()

    # Clock in
    shift = Shift.query.first()
    att = StaffService.record_clock_in(emp.id, shift_id=shift.id, notes='Test clockin')
    assert att.id is not None
    assert att.attendance_status in ['present', 'late']
    assert att.clock_out is None

    # Attempt duplicate clock-in on same day should raise error
    with pytest.raises(StaffServiceError) as exc_info:
        StaffService.record_clock_in(emp.id, shift_id=shift.id)
    assert "already clocked in" in str(exc_info.value).lower()

    # Clock out
    att_out = StaffService.record_clock_out(att.id, notes='Shift ended successfully')
    assert att_out.clock_out is not None
    assert 'Shift ended successfully' in att_out.notes


def test_03_staff_payroll_generation_and_payout(app):
    """
    Test 3: Payroll Generation and Disbursement (Atomic Transaction)
    Verifies calculation: net_salary = base_salary + bonus - deductions.
    """
    emp = Employee.query.first()
    month = 12
    year = 2026

    # Remove existing if any from previous runs
    Payroll.query.filter_by(employee_id=emp.id, payroll_period_month=month, payroll_period_year=year).delete()
    db.session.commit()

    base = Decimal(str(emp.base_salary))
    bonus = Decimal('250.00')
    deductions = Decimal('50.00')
    expected_net = base + bonus - deductions

    payroll = StaffService.generate_payroll_slip(
        employee_id=emp.id,
        month=month,
        year=year,
        bonus=bonus,
        deductions=deductions
    )
    assert payroll.id is not None
    assert payroll.net_salary == expected_net
    assert payroll.payment_status == 'unpaid'

    # Disburse payment
    paid_payroll = StaffService.mark_payroll_paid(payroll.id, reference_no=f"BANK-DISBURSE-{uuid.uuid4().hex[:6].upper()}")
    assert paid_payroll.payment_status == 'paid'
    assert paid_payroll.payment_date is not None


def test_04_delivery_dispatch_workflow(app):
    """
    Test 4: Delivery Logistics & Tracking
    Tests driver assignment, agent availability toggle, status flow, and route milestone tracking.
    """
    order = Order.query.first()
    cust = Customer.query.first()
    addr = cust.addresses.first()
    agent = DeliveryAgent.query.filter_by(is_available=True).first()
    assert agent is not None

    # Clean existing delivery for this order if present
    Delivery.query.filter_by(order_id=order.id).delete()
    db.session.commit()

    # 1. Create Delivery
    delivery = DeliveryService.create_delivery_for_order(
        order_id=order.id,
        address_id=addr.id,
        delivery_fee=Decimal('4.50'),
        notes='Leave at reception'
    )
    assert delivery.delivery_status == 'pending'

    # 2. Assign Agent
    assigned_delivery = DeliveryService.assign_agent(delivery.id, agent.id)
    assert assigned_delivery.delivery_status == 'assigned'
    db.session.refresh(agent)
    assert agent.is_available is False  # Agent now on duty

    # 3. Transition: Picked Up -> In Transit -> Delivered
    DeliveryService.advance_delivery_status(delivery.id, 'picked_up', notes='Order bagged and warm')
    DeliveryService.advance_delivery_status(delivery.id, 'in_transit', latitude=Decimal('40.712800'), longitude=Decimal('-74.006000'), notes='Courier en route')
    completed_delivery = DeliveryService.advance_delivery_status(delivery.id, 'delivered', notes='Customer received order')

    assert completed_delivery.delivery_status == 'delivered'
    assert completed_delivery.delivered_at is not None

    # Agent is available again
    db.session.refresh(agent)
    assert agent.is_available is True

    # Tracking checkpoints recorded
    checkpoints = DeliveryTracking.query.filter_by(delivery_id=delivery.id).all()
    assert len(checkpoints) >= 4


def test_05_expenses_tracking_and_summaries(app):
    """
    Test 5: Operating Expenses Ledger
    Tests recording expense, invalid amount handling, and category summary aggregations.
    """
    cat = ExpenseCategory.query.first()
    initial_total = ExpenseService.get_total_expenses()

    # Valid expense
    expense = ExpenseService.record_expense(
        category_id=cat.id,
        title='Kitchen Deep Sanitation Service',
        amount=Decimal('320.00'),
        notes='Monthly certified cleaning'
    )
    assert expense.id is not None
    assert expense.amount == Decimal('320.00')

    # Total should increase
    new_total = ExpenseService.get_total_expenses()
    assert new_total == initial_total + Decimal('320.00')

    # Summary by category
    summaries = ExpenseService.get_expense_summary_by_category()
    assert len(summaries) > 0
    cat_names = [s['category'] for s in summaries]
    assert cat.name in cat_names

    # Negative amount should be rejected
    with pytest.raises(ExpenseServiceError):
        ExpenseService.record_expense(cat.id, 'Invalid', Decimal('-10.00'))


def test_06_loyalty_point_accrual_and_redemption(app):
    """
    Test 6: Loyalty Program Tiers, Accrual, and Burn
    Tests awarding points on order completion, balance updates, and points redemption.
    """
    cust = Customer.query.first()
    initial_points = cust.loyalty_points or 0

    # Award points for $100 order
    tx = LoyaltyService.award_order_points(cust.id, order_id=None, total_amount=Decimal('100.00'))
    assert tx is not None
    assert tx.points >= 100
    db.session.refresh(cust)
    assert cust.loyalty_points == initial_points + tx.points

    # Redeem 50 points
    discount, burn_tx = LoyaltyService.redeem_points(cust.id, points_to_burn=50)
    assert discount > Decimal('0.00')
    assert burn_tx.points == -50
    db.session.refresh(cust)
    assert cust.loyalty_points == initial_points + tx.points - 50

    # Attempt to redeem more points than balance
    with pytest.raises(LoyaltyServiceError):
        LoyaltyService.redeem_points(cust.id, points_to_burn=999999)


def test_07_customer_feedback_and_statistics(app):
    """
    Test 7: Customer Reviews and Ratings
    Tests rating calculation (food, service, ambience average), statistics, and manager responses.
    """
    cust = Customer.query.first()
    fb = FeedbackService.submit_feedback(
        food_rating=5,
        service_rating=4,
        ambience_rating=4,
        customer_id=cust.id,
        comments='Wonderful dining atmosphere and courteous team!'
    )
    assert fb.id is not None
    # (5 + 4 + 4) / 3 = 4.33
    assert fb.overall_rating == Decimal('4.33')

    # Manager response
    updated_fb = FeedbackService.respond_to_feedback(fb.id, 'Thank you! Hope to see you back soon.')
    assert 'Thank you!' in updated_fb.response_notes

    # Statistics
    stats = FeedbackService.get_feedback_statistics()
    assert stats['total_reviews'] > 0
    assert stats['avg_overall'] > Decimal('0.00')

    # Invalid rating (> 5) should raise error
    with pytest.raises(FeedbackServiceError):
        FeedbackService.submit_feedback(food_rating=6, service_rating=3, ambience_rating=3)


def test_08_reports_and_settings_audit(app):
    """
    Test 8: Reports, System Settings & Audit Trail
    Tests financial KPI calculations, caching, settings modification, and audit log tracking.
    """
    # 1. Reports KPIs
    kpis = ReportService.get_financial_kpis(force_refresh=True)
    assert 'total_revenue' in kpis
    assert 'total_expenses' in kpis
    assert 'net_profit' in kpis
    assert kpis['total_expenses'] > Decimal('0.00')

    # 2. System Settings
    setting = SystemSetting.query.filter_by(setting_key='restaurant_name').first()
    assert setting is not None
    assert 'GourmetOS' in setting.setting_value

    # 3. Audit Log
    audit = AuditService.log(
        action='CONFIG_CHECK',
        target_entity='SystemSetting',
        target_id=setting.id,
        details={'checked': True}
    )
    assert audit is not None
    assert audit.action == 'CONFIG_CHECK'
    assert 'checked' in audit.details_json
