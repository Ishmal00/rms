from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models.auth import User
from app.models.billing import PaymentMethod
from app.models.customers import Customer
from app.models.inventory import InventoryItem
from app.models.menu import MenuItem
from app.models.notifications import Notification
from app.models.orders import Order
from app.models.settings import AuditLog
from app.models.staff import Department, Employee, Shift
from app.services.billing_service import BillingService, PaymentProcessingError
from app.services.customer_service import CustomerService
from app.services.employee_service import EmployeeService
from app.services.notification_service import NotificationService
from app.services.order_service import OrderPlacementError, OrderService


def create_test_app():
    database_url = TestingConfig.SQLALCHEMY_DATABASE_URI
    if not database_url:
        raise RuntimeError('Tests aborted: TEST_DATABASE_URL must target restaurant_test_db.')
    database_name = (make_url(database_url).database or '').lower()
    if database_name != 'restaurant_test_db':
        raise RuntimeError(
            'Tests aborted: TEST_DATABASE_URL must target restaurant_test_db; '
            f'got {database_name!r}.'
        )
    return create_app('testing')


@pytest.fixture(scope='module')
def app():
    application = create_test_app()
    with application.app_context():
        import app.models
        from app.seeds.seed_data import seed_database

        db.drop_all()
        db.create_all()
        seed_database()
        yield application


def login_as(client, user):
    with client.session_transaction() as session:
        session['_user_id'] = str(user.id)
        session['_fresh'] = True


def test_customer_routes_crud_search_and_detail(app):
    admin = User.query.filter_by(username='admin').first()
    client = app.test_client()
    login_as(client, admin)

    token = uuid4().hex[:8]
    assert client.get('/customers/new').status_code == 200
    response = client.post('/customers/new', data={
        'name': f'Test Customer {token}',
        'phone': f'+1-555-{token[:4]}',
        'email': f'{token}@example.test',
        'notes': 'Created in module test'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert f'Test Customer {token}'.encode() in response.data

    customer = Customer.query.filter_by(email=f'{token}@example.test').first()
    assert customer is not None
    assert AuditLog.query.filter_by(target_entity='Customer', target_id=customer.id).count() == 1

    search_response = client.get(f'/customers/?q={token}')
    assert search_response.status_code == 200
    assert customer.name.encode() in search_response.data

    detail_response = client.get(f'/customers/{customer.id}')
    assert detail_response.status_code == 200
    assert b'Order History' in detail_response.data
    assert b'Loyalty Points' in detail_response.data

    response = client.post(f'/customers/{customer.id}/edit', data={
        'name': f'Updated Customer {token}',
        'phone': f'+1-555-{token[:4]}',
        'email': f'{token}@example.test',
        'notes': 'Updated'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert customer.name == f'Updated Customer {token}'

    response = client.post(f'/customers/{customer.id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert Customer.query.filter_by(id=customer.id).first() is None
    assert Customer.query_with_deleted().filter_by(id=customer.id).first().is_deleted
    assert AuditLog.query.filter_by(target_entity='Customer', target_id=customer.id).count() == 3


def test_employee_routes_crud_department_designation_and_shift(app):
    admin = User.query.filter_by(username='admin').first()
    department = Department.query.first()
    shift = Shift.query.first()
    client = app.test_client()
    login_as(client, admin)
    employee_code = f'TEST-{uuid4().hex[:8]}'
    employee_data = {
        'employee_code': employee_code,
        'first_name': 'Test',
        'last_name': 'Employee',
        'department_id': str(department.id),
        'designation': 'Test Cook',
        'shift_id': str(shift.id),
        'hire_date': date.today().isoformat(),
        'base_salary': '2500.00',
        'emergency_contact': '555-0101'
    }

    assert client.get('/staff/employees/new').status_code == 200
    response = client.post('/staff/employees/new', data=employee_data, follow_redirects=True)
    assert response.status_code == 200
    employee = Employee.query.filter_by(employee_code=employee_code).first()
    assert employee is not None
    assert employee.department_id == department.id
    assert employee.designation == 'Test Cook'
    assert employee.shift_id == shift.id

    employee_data['designation'] = 'Senior Test Cook'
    assert client.get(f'/staff/employees/{employee.id}/edit').status_code == 200
    response = client.post(
        f'/staff/employees/{employee.id}/edit',
        data=employee_data,
        follow_redirects=True
    )
    assert response.status_code == 200
    assert employee.designation == 'Senior Test Cook'
    assert AuditLog.query.filter_by(target_entity='Employee', target_id=employee.id).count() == 2

    response = client.post(f'/staff/employees/{employee.id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert Employee.query.filter_by(id=employee.id).first() is None
    assert Employee.query_with_deleted().filter_by(id=employee.id).first().is_deleted
    assert AuditLog.query.filter_by(target_entity='Employee', target_id=employee.id).count() == 3


def test_order_notifications_are_transactional_and_low_stock_alerts_are_created(app):
    admin = User.query.filter_by(username='admin').first()
    inventory_item = InventoryItem.query.filter_by(name='Ribeye Cut Beef').first()
    menu_item = MenuItem.query.filter_by(slug='bruschetta').first()
    original_stock = Decimal(str(inventory_item.current_stock))
    baseline_orders = Order.query.count()
    baseline_notification_count = Notification.query.filter_by(
        user_id=admin.id,
        notification_type='new_order'
    ).count()

    with pytest.raises(OrderPlacementError, match='Simulated failure'):
        OrderService.place_order(
            order_type_slug='takeaway',
            items_data=[{'menu_item_id': menu_item.id, 'quantity': 1}],
            user_id=admin.id,
            simulate_failure=True
        )
    assert Order.query.count() == baseline_orders
    assert Notification.query.filter_by(
        user_id=admin.id,
        notification_type='new_order'
    ).count() == baseline_notification_count
    db.session.refresh(inventory_item)
    assert Decimal(str(inventory_item.current_stock)) == original_stock

    inventory_item.current_stock = Decimal('10.50')
    db.session.commit()
    order = OrderService.place_order(
        order_type_slug='takeaway',
        items_data=[{'menu_item_id': menu_item.id, 'quantity': 1}],
        user_id=admin.id
    )
    assert Notification.query.filter_by(
        user_id=admin.id,
        notification_type='new_order'
    ).count() == baseline_notification_count + 1
    low_stock_notification = Notification.query.filter_by(
        user_id=admin.id,
        notification_type='low_stock'
    ).order_by(Notification.id.desc()).first()
    assert low_stock_notification is not None
    assert 'Ribeye Cut Beef' in low_stock_notification.message

    inventory_item.current_stock = original_stock
    db.session.commit()
    assert order is not None


def test_payment_notification_and_user_scoped_mark_as_read(app):
    admin = User.query.filter_by(username='admin').first()
    menu_item = MenuItem.query.filter_by(slug='bruschetta').first()
    inventory_item = InventoryItem.query.first()
    original_stock = Decimal(str(inventory_item.current_stock))
    inventory_item.current_stock = Decimal('30.00')
    db.session.commit()

    order = OrderService.place_order(
        order_type_slug='takeaway',
        items_data=[{'menu_item_id': menu_item.id, 'quantity': 1}],
        user_id=admin.id
    )
    method = PaymentMethod.query.first()
    existing_payment_notifications = Notification.query.filter_by(
        user_id=admin.id,
        notification_type='payment_received'
    ).count()
    with pytest.raises(PaymentProcessingError, match='Forced test error'):
        BillingService.process_payment(
            invoice_id=order.invoice.id,
            payment_method_id=method.id,
            amount='1.00',
            user_id=admin.id,
            simulate_failure=True
        )
    assert Notification.query.filter_by(
        user_id=admin.id,
        notification_type='payment_received'
    ).count() == existing_payment_notifications

    BillingService.process_payment(
        invoice_id=order.invoice.id,
        payment_method_id=method.id,
        amount='1.00',
        user_id=admin.id
    )
    payment_notification = Notification.query.filter_by(
        user_id=admin.id,
        notification_type='payment_received'
    ).order_by(Notification.id.desc()).first()
    assert payment_notification is not None
    assert order.invoice.invoice_number in payment_notification.message

    other_user = User.query.filter(User.id != admin.id).first()
    own_notification = NotificationService.create_for_user(
        admin.id,
        'Test read state',
        'Only the owner can mark this as read.',
        'test'
    )
    foreign_notification = NotificationService.create_for_user(
        other_user.id,
        'Other user notification',
        'This belongs to a different user.',
        'test'
    )
    db.session.commit()

    client = app.test_client()
    login_as(client, admin)
    notification_page = client.get('/notifications/')
    assert notification_page.status_code == 200
    assert b'aria-label="Notifications"' in notification_page.data
    response = client.post(f'/notifications/{own_notification.id}/read', follow_redirects=True)
    assert response.status_code == 200
    db.session.refresh(own_notification)
    db.session.refresh(foreign_notification)
    assert own_notification.is_read
    assert not foreign_notification.is_read

    inventory_item.current_stock = original_stock
    db.session.commit()
