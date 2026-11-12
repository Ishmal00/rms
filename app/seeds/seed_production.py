"""Seed the minimum production access and configuration records."""

import os

from app.extensions import db
from app.models.auth import Permission, Role, RolePermission, User
from app.models.settings import SystemSetting


ROLES = [
    ('Admin', 'admin', 'Full administrative system access'),
    ('Manager', 'manager', 'Restaurant floor, staff, and inventory management'),
    ('Waiter', 'waiter', 'Table ordering and customer service access'),
    ('Kitchen', 'kitchen', 'Kitchen order display and stock monitoring'),
    ('Cashier', 'cashier', 'Order checkout and billing operations'),
]

PERMISSIONS = [
    ('Manage Authentication & Users', 'auth.manage', 'auth', 'Create, update, and manage users and roles'),
    ('View Menu Catalog', 'menu.view', 'menu', 'View menu items and categories'),
    ('Manage Menu Catalog', 'menu.manage', 'menu', 'Create and modify menu items, categories, recipes'),
    ('View Inventory', 'inventory.view', 'inventory', 'View inventory levels and movements'),
    ('Manage Inventory', 'inventory.manage', 'inventory', 'Adjust inventory stock, suppliers, and items'),
    ('View Tables & Reservations', 'tables.view', 'tables', 'View table layout and customer bookings'),
    ('Manage Tables & Reservations', 'tables.manage', 'tables', 'Assign tables, handle customer bookings'),
    ('POS Ordering', 'orders.pos', 'orders', 'Access POS terminal to take customer orders'),
    ('Manage Orders', 'orders.manage', 'orders', 'Manage, view, and cancel orders'),
    ('Kitchen Display', 'kitchen.view', 'kitchen', 'View and progress kitchen order tickets'),
    ('Manage Billing', 'billing.manage', 'billing', 'Process invoice payments and apply coupons'),
    ('Manage System Settings', 'settings.manage', 'settings', 'View and modify system settings'),
    ('Manage Trash', 'admin.trash', 'admin', 'View and restore soft-deleted records'),
    ('Delete Expenses', 'expenses.delete', 'expenses', 'Delete recorded expenses'),
    ('Manage Payroll', 'payroll.manage', 'payroll', 'Generate and disburse payroll'),
    ('View Reports', 'reports.view', 'reports', 'View operational and financial reports'),
    ('Manage Staff', 'staff.manage', 'staff', 'View staff and manage attendance'),
    ('Manage Customers', 'customers.manage', 'customers', 'Create, update, and remove customer records'),
    ('Manage Expenses', 'expenses.manage', 'expenses', 'View and manage expense records'),
    ('Manage Feedback', 'feedback.manage', 'feedback', 'View and manage customer feedback'),
    ('Manage Loyalty', 'loyalty.manage', 'loyalty', 'Manage loyalty tiers, rewards, and customer points'),
    ('Manage Delivery', 'delivery.manage', 'delivery', 'Manage delivery dispatch and driver records'),
    ('Manage Notifications', 'notifications.manage', 'notifications', 'View and manage in-app notifications'),
]

MANAGER_PERMISSIONS = {
    'menu.view', 'menu.manage', 'inventory.view', 'inventory.manage',
    'tables.view', 'tables.manage', 'reports.view', 'staff.manage',
    'customers.manage', 'expenses.manage', 'feedback.manage',
    'loyalty.manage', 'delivery.manage',
}

SETTINGS = [
    ('restaurant_name', 'Restaurant', 'string', 'Restaurant business name', True),
    ('currency', 'USD', 'string', 'Base financial currency', True),
    ('tax_rate_percent', '0', 'number', 'Tax rate percentage', True),
    ('service_charge_percent', '0', 'number', 'Default service charge percentage', True),
    ('operating_hours', 'Not configured', 'string', 'Restaurant operating hours', True),
    ('contact_email', '', 'string', 'General inquiries contact email', True),
]


def seed_production():
    """Create only RBAC records, default settings, and the configured admin user."""
    admin_password = os.environ.get('ADMIN_PASSWORD')
    if not admin_password:
        raise RuntimeError(
            'ADMIN_PASSWORD is required to seed production; refusing to create '
            'an admin with a default password.'
        )

    roles = {}
    for name, slug, description in ROLES:
        role = Role.query.filter_by(slug=slug).first()
        if role is None:
            role = Role(name=name, slug=slug, description=description)
            db.session.add(role)
            db.session.flush()
        roles[slug] = role

    permissions = {}
    for name, slug, module, description in PERMISSIONS:
        permission = Permission.query.filter_by(slug=slug).first()
        if permission is None:
            permission = Permission(
                name=name,
                slug=slug,
                module=module,
                description=description,
            )
            db.session.add(permission)
            db.session.flush()
        permissions[slug] = permission

    grants = {
        'admin': set(permissions),
        'manager': set(MANAGER_PERMISSIONS),
        'waiter': {'orders.pos', 'orders.manage', 'billing.manage'},
        'cashier': {'orders.pos', 'orders.manage', 'billing.manage'},
        'kitchen': {'kitchen.view'},
    }
    for role_slug in roles:
        grants[role_slug].add('notifications.manage')
        for permission_slug in grants[role_slug]:
            permission = permissions[permission_slug]
            existing = RolePermission.query.filter_by(
                role_id=roles[role_slug].id,
                permission_id=permission.id,
            ).first()
            if existing is None:
                db.session.add(RolePermission(
                    role_id=roles[role_slug].id,
                    permission_id=permission.id,
                ))

    admin = User.query.filter_by(username='admin').first()
    if admin is None:
        admin = User(
            username='admin',
            email='admin@restaurant.local',
            full_name='Administrator',
            role_id=roles['admin'].id,
        )
        db.session.add(admin)
    else:
        admin.role_id = roles['admin'].id
    admin.set_password(admin_password)

    for key, value, setting_type, description, is_public in SETTINGS:
        setting = SystemSetting.query.filter_by(setting_key=key).first()
        if setting is None:
            db.session.add(SystemSetting(
                setting_key=key,
                setting_value=value,
                setting_type=setting_type,
                description=description,
                is_public=is_public,
            ))

    db.session.commit()


def main():
    if not os.environ.get('ADMIN_PASSWORD'):
        raise RuntimeError(
            'ADMIN_PASSWORD is required to seed production; refusing to create '
            'an admin with a default password.'
        )

    from app import create_app

    app = create_app('production')
    with app.app_context():
        seed_production()


if __name__ == '__main__':
    main()
