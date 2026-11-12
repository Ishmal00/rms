import unittest
from datetime import date
from decimal import Decimal
from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models.auth import User, Role, Permission
from app.models.menu import Category, MenuItem, ItemVariant, Ingredient
from app.models.inventory import Supplier, InventoryItem, StockMovement
from app.models.tables import RestaurantTable, Reservation
from app.models.expenses import Expense, ExpenseCategory
from app.services.cache_service import cache
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


class Phase1VerificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_test_app()
        with cls.app.app_context():
            import app.models
            from app.seeds.seed_data import seed_database

            db.drop_all()
            db.create_all()
            seed_database()

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        self.app_context.pop()

    def test_01_models_and_counts(self):
        """Verify all 14 Phase 1 models have seeded data."""
        self.assertGreaterEqual(User.query.count(), 3)
        self.assertGreaterEqual(Role.query.count(), 5)
        self.assertGreaterEqual(Permission.query.count(), 7)
        self.assertGreaterEqual(Category.query.count(), 4)
        self.assertGreaterEqual(MenuItem.query.count(), 7)
        self.assertGreaterEqual(ItemVariant.query.count(), 5)
        self.assertGreaterEqual(Ingredient.query.count(), 6)
        self.assertGreaterEqual(Supplier.query.count(), 3)
        self.assertGreaterEqual(InventoryItem.query.count(), 5)
        self.assertGreaterEqual(StockMovement.query.count(), 5)
        self.assertGreaterEqual(RestaurantTable.query.count(), 8)
        self.assertGreaterEqual(Reservation.query.count(), 3)
        print("Test 1 passed: All 14 models populated with seeded data.")

    def test_02_password_hashing_and_rbac(self):
        """Verify password hashing and role-based permissions."""
        admin = User.query.filter_by(username='admin').first()
        self.assertIsNotNone(admin)
        self.assertTrue(admin.check_password('Admin@123'))
        self.assertFalse(admin.check_password('WrongPassword'))
        self.assertTrue(admin.has_role('admin'))
        self.assertTrue(admin.has_permission('menu.manage'))

        waiter = User.query.filter_by(username='waiter').first()
        self.assertIsNotNone(waiter)
        self.assertTrue(waiter.check_password('Waiter@123'))
        self.assertTrue(waiter.has_role('waiter'))
        self.assertTrue(waiter.has_permission('orders.pos'))
        self.assertTrue(waiter.has_permission('orders.manage'))
        self.assertTrue(waiter.has_permission('billing.manage'))
        manager = User.query.filter_by(username='manager').first()
        self.assertTrue(manager.has_permission('reports.view'))
        self.assertTrue(manager.has_permission('staff.manage'))
        self.assertTrue(manager.has_permission('inventory.manage'))
        self.assertTrue(manager.has_permission('menu.manage'))
        print("Test 2 passed: Password hashing and RBAC verified.")

    def test_03_base_model_soft_delete_and_restore(self):
        """Verify BaseModel soft delete hides items from normal queries and allows restore."""
        admin = User.query.filter_by(username='admin').first()
        
        # Create a temporary menu item for test
        cat = Category.query.first()
        temp_item = MenuItem(
            category_id=cat.id,
            name='Temporary Test Dish',
            slug='temp-test-dish-unique',
            description='Test item for soft delete',
            base_price=9.99,
            created_by=admin.id
        )
        db.session.add(temp_item)
        db.session.commit()
        item_id = temp_item.id

        # Verify it shows in normal query
        found = MenuItem.query.filter_by(id=item_id).first()
        self.assertIsNotNone(found)
        self.assertFalse(found.is_deleted)
        self.assertEqual(found.status, 'active')

        # Soft delete it
        found.soft_delete(user_id=admin.id)
        db.session.commit()

        # Verify standard query filters it out automatically!
        deleted_search = MenuItem.query.filter_by(id=item_id).first()
        self.assertIsNone(deleted_search)

        # Verify query_trash includes it
        in_trash = MenuItem.query_trash().filter(MenuItem.id == item_id).first()
        self.assertIsNotNone(in_trash)
        self.assertTrue(in_trash.is_deleted)
        self.assertEqual(in_trash.status, 'deactive')
        self.assertIsNotNone(in_trash.deleted_at)
        self.assertEqual(in_trash.deleted_by, admin.id)

        # Restore it
        in_trash.restore(user_id=admin.id)
        db.session.commit()

        # Verify it reappears in normal query
        restored = MenuItem.query.filter_by(id=item_id).first()
        self.assertIsNotNone(restored)
        self.assertFalse(restored.is_deleted)
        self.assertEqual(restored.status, 'active')

        # Cleanup test item
        db.session.delete(restored)
        db.session.commit()
        print("Test 3 passed: BaseModel soft delete, global filtering, and restore verified.")

    def test_04_cache_service(self):
        """Verify cache set, get, pattern invalidation."""
        cache.set('test:key:1', {'hello': 'world'}, timeout=60)
        cached_val = cache.get('test:key:1')
        self.assertEqual(cached_val, {'hello': 'world'})

        cache.delete_pattern('test:*')
        self.assertIsNone(cache.get('test:key:1'))
        print("Test 4 passed: Cache operations and pattern invalidation verified.")

    def test_05_http_routes_and_authentication(self):
        """Verify HTTP endpoints and redirect behaviors."""
        # Unauthenticated access to dashboard should redirect to login
        res = self.client.get('/dashboard')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/auth/login', res.headers['Location'])

        # Login page renders 200 OK
        res = self.client.get('/auth/login')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Gourmet', res.data)

        # Test login with test client
        with self.client:
            # Login as admin
            res = self.client.post('/auth/login', data={
                'identity': 'admin',
                'password': 'Admin@123',
                'remember_me': False
            }, follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            self.assertIn(b'Operational Dashboard', res.data)

            # Test accessing views authenticated
            menu_res = self.client.get('/menu/')
            self.assertEqual(menu_res.status_code, 200)
            self.assertIn(b'Menu Catalog', menu_res.data)

            tables_res = self.client.get('/tables/')
            self.assertEqual(tables_res.status_code, 200)
            self.assertIn(b'Floor Plan', tables_res.data)

            inv_res = self.client.get('/inventory/')
            self.assertEqual(inv_res.status_code, 200)
            self.assertIn(b'Inventory &amp; Supplies', inv_res.data)

            trash_res = self.client.get('/admin/trash')
            self.assertEqual(trash_res.status_code, 200)
            self.assertIn(b'Trash & Soft-Delete Recovery', trash_res.data)

            users_res = self.client.get('/admin/users')
            self.assertEqual(users_res.status_code, 200)
            self.assertIn(b'Staff & System Users', users_res.data)

            # Logout
            logout_res = self.client.get('/auth/logout', follow_redirects=True)
            self.assertEqual(logout_res.status_code, 200)
            self.assertIn(b'Sign In', logout_res.data)

        print("Test 5 passed: All HTTP routes, authentication, and layout rendering verified.")

    def test_06_login_rejects_external_next_url(self):
        response = self.client.post(
            '/auth/login?next=//evil.com',
            data={
                'identity': 'admin',
                'password': 'Admin@123',
                'remember_me': False
            },
            follow_redirects=False
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].startswith('/'))
        self.assertFalse(response.headers['Location'].startswith('//'))
        self.assertNotIn('evil.com', response.headers['Location'])

    def test_07_role_permissions_protect_operational_routes(self):
        response = self.client.post('/auth/login', data={
            'identity': 'waiter',
            'password': 'Waiter@123',
            'remember_me': False
        })
        self.assertEqual(response.status_code, 302)

        denied_routes = (
            '/admin/users',
            '/admin/trash',
            '/settings/',
            '/staff/payroll',
            '/reports/',
            '/staff/',
            '/inventory/',
            '/menu/',
            '/kitchen/',
        )
        for route in denied_routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 403)

        self.assertEqual(self.client.post('/expenses/delete/1').status_code, 403)
        self.assertEqual(self.client.get('/orders/pos').status_code, 200)
        self.assertEqual(self.client.get('/orders/').status_code, 200)
        self.assertEqual(self.client.get('/billing/invoices/999').status_code, 404)

    def test_08_admin_can_soft_delete_expense(self):
        admin = User.query.filter_by(username='admin').first()
        category = ExpenseCategory.query.first()
        expense = Expense(
            category_id=category.id,
            title='Expense delete authorization test',
            amount=Decimal('1.00'),
            expense_date=date.today()
        )
        db.session.add(expense)
        db.session.commit()
        expense_id = expense.id

        self.client.post('/auth/login', data={
            'identity': 'admin',
            'password': 'Admin@123',
            'remember_me': False
        })
        response = self.client.post(f'/expenses/delete/{expense_id}')

        self.assertEqual(response.status_code, 302)
        deleted = Expense.query_with_deleted().filter_by(id=expense_id).first()
        self.assertTrue(deleted.is_deleted)
        self.assertEqual(deleted.deleted_by, admin.id)
        self.assertIsNotNone(deleted.deleted_at)


if __name__ == '__main__':
    unittest.main()
