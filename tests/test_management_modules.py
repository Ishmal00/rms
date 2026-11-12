from datetime import date
from decimal import Decimal
import re
from uuid import uuid4

import pytest
from flask import g
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
    g.pop('_login_user', None)


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


def test_customer_search_and_filter_work_with_server_pagination(app):
    admin = User.query.filter_by(username='admin').first()
    token = uuid4().hex[:8]
    customers = [
        Customer(
            name=f'Pagination {token} {index:02d}',
            phone=f'+1-555-{uuid4().hex[:8]}',
            email=f'{token}-{index}@example.test',
            status='active'
        )
        for index in range(11)
    ]
    db.session.add_all(customers)
    db.session.commit()

    client = app.test_client()
    login_as(client, admin)
    response = client.get(f'/customers/?q={token}&status=active&page=2')
    assert response.status_code == 200
    for customer in customers[:10]:
        assert customer.name.encode() not in response.data
    assert customers[10].name.encode() in response.data


def test_customer_status_toggle_is_permissioned_post_and_audited(app):
    admin = User.query.filter_by(username='admin').first()
    customer = Customer.query.filter_by(name='Emily Watson').first()
    client = app.test_client()
    login_as(client, admin)

    assert client.get(f'/customers/{customer.id}/toggle-status').status_code == 405
    response = client.post(f'/customers/{customer.id}/toggle-status', follow_redirects=True)
    assert response.status_code == 200
    db.session.refresh(customer)
    assert customer.status == 'deactive'
    assert AuditLog.query.filter_by(
        target_entity='Customer',
        target_id=customer.id,
        action='DEACTIVATE'
    ).count() == 1


def test_admin_trash_restores_soft_deleted_model_types(app):
    from app.models import (
        Category,
        CustomerFeedback,
        DeliveryAgent,
        Employee,
        Expense,
        InventoryItem,
        MenuItem,
        Notification,
        RestaurantTable,
        Reservation,
        Supplier,
    )

    admin = User.query.filter_by(username='admin').first()
    model_types = (
        Customer,
        Employee,
        Expense,
        CustomerFeedback,
        DeliveryAgent,
        Reservation,
        Notification,
        MenuItem,
        Category,
        InventoryItem,
        Supplier,
        RestaurantTable,
    )
    client = app.test_client()
    login_as(client, admin)

    for model in model_types:
        record = model.query.filter_by(is_deleted=False).first()
        assert record is not None, f'Expected seeded {model.__name__} record'
        record.soft_delete(user_id=admin.id)
        db.session.commit()

        entity_type = {
            'RestaurantTable': 'table',
        }.get(model.__name__, re.sub(r'(?<!^)(?=[A-Z])', '_', model.__name__).lower())
        response = client.post(f'/admin/restore/{entity_type}/{record.id}')
        assert response.status_code == 302
        db.session.expire_all()

        restored = model.query_with_deleted().filter_by(id=record.id).first()
        assert restored is not None
        assert restored.is_deleted is False
        assert restored.deleted_at is None
        assert restored.deleted_by is None
        assert restored.status == 'active'
        assert AuditLog.query.filter_by(
            action='RESTORE',
            target_entity=model.__name__,
            target_id=record.id
        ).count() == 1


def test_admin_trash_search_pagination_and_deleted_metadata(app):
    admin = User.query.filter_by(username='admin').first()
    token = uuid4().hex[:8]
    customers = [
        Customer(
            name=f'Trash Search {token} {index:02d}',
            phone=f'+1-555-{uuid4().hex[:8]}',
            email=f'trash-{token}-{index}@example.test'
        )
        for index in range(21)
    ]
    db.session.add_all(customers)
    db.session.flush()
    for customer in customers:
        customer.soft_delete(user_id=admin.id)
    db.session.commit()

    client = app.test_client()
    login_as(client, admin)
    response = client.get(
        f'/admin/trash?q={token}&entity_type=customer&page=2'
    )
    assert response.status_code == 200
    assert b'Showing 21 matching deleted record(s).' in response.data
    assert f'Trash Search {token} 20'.encode() in response.data
    assert f'Trash Search {token} 00'.encode() not in response.data
    assert b'System Administrator' in response.data
    assert b'Deleted At' in response.data


def test_admin_trash_restore_rejects_non_admin(app):
    waiter = User.query.filter_by(username='waiter').first()
    assert waiter.role.slug == 'waiter'
    assert not waiter.has_role('admin')
    client = app.test_client()
    login_as(client, waiter)
    with client.session_transaction() as session:
        assert session['_user_id'] == str(waiter.id)

    assert client.get('/admin/trash').status_code == 403
    assert client.post('/admin/restore/customer/1').status_code == 403


def test_step_4a_list_pages_render_for_admin(app):
    admin = User.query.filter_by(username='admin').first()
    client = app.test_client()
    login_as(client, admin)
    for path in (
        '/customers/?q=Emily&status=active&page=1',
        '/staff/?q=EMP&status=active&page=1',
        '/expenses/?q=Electricity&category_id=1&status=active',
        '/feedback/?q=world&rating=4&status=active&page=1',
        '/loyalty/?q=Emily&status=active&transaction_type=earn&page=1',
        '/delivery/?q=ORD&delivery_status=pending&status=active&page=1',
        '/tables/?q=T&zone=Indoor&status=available&active_status=active&table_page=1',
        '/tables/?reservation_q=Eleanor&reservation_status=confirmed&reservation_page=1',
        '/menu/?q=Bruschetta&status=active&page=1',
        '/notifications/?q=Welcome&type=system&read=unread&status=active&page=1',
        '/admin/users?q=admin&status=active&page=1',
        '/expenses/api/data?draw=1&start=0&length=10&search%5Bvalue%5D=Electricity&category_id=1&status=active',
        '/menu/api/data?draw=1&start=0&length=10&search%5Bvalue%5D=Bruschetta'
    ):
        response = client.get(path)
        assert response.status_code == 200, f'{path} returned {response.status_code}'


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
