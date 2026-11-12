from datetime import datetime, timedelta, time, date
from app.extensions import db
from app.models.auth import Role, Permission, RolePermission, User
from app.models.menu import Category, SubCategory, MenuItem, ItemVariant, Ingredient
from app.models.inventory import Supplier, InventoryItem, StockMovement
from app.models.tables import RestaurantTable, Reservation
from app.models.customers import Customer, Address
from app.models.orders import OrderType
from app.models.billing import Tax, Discount, Coupon, PaymentMethod
from app.models.staff import Department, Employee, Shift, Attendance, Payroll
from app.models.delivery import DeliveryAgent, Delivery, DeliveryTracking
from app.models.expenses import ExpenseCategory, Expense
from app.models.loyalty import LoyaltyProgram, LoyaltyTransaction, Reward
from app.models.feedback import CustomerFeedback
from app.models.settings import SystemSetting, AuditLog
from app.models.notifications import Notification
from app.services.order_service import OrderService


def seed_database():
    """Populates the database with initial Phase 1 & Phase 2 seed data."""
    print("Beginning database seeding (Phase 1 & Phase 2)...")

    # ==========================================
    # 1. ROLES & PERMISSIONS
    # ==========================================
    roles_data = [
        ('Admin', 'admin', 'Full administrative system access'),
        ('Manager', 'manager', 'Restaurant floor, staff, and inventory management'),
        ('Waiter', 'waiter', 'Table ordering and customer service access'),
        ('Kitchen', 'kitchen', 'Kitchen order display and stock monitoring'),
        ('Cashier', 'cashier', 'Order checkout and billing operations'),
    ]

    roles = {}
    for name, slug, desc in roles_data:
        role = Role.query.filter_by(slug=slug).first()
        if not role:
            role = Role(name=name, slug=slug, description=desc)
            db.session.add(role)
            db.session.flush()
        roles[slug] = role

    permissions_data = [
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
    ]

    perms = {}
    for name, slug, mod, desc in permissions_data:
        perm = Permission.query.filter_by(slug=slug).first()
        if not perm:
            perm = Permission(name=name, slug=slug, module=mod, description=desc)
            db.session.add(perm)
            db.session.flush()
        perms[slug] = perm

    # Assign permissions to roles
    for slug, perm in perms.items():
        if not RolePermission.query.filter_by(role_id=roles['admin'].id, permission_id=perm.id).first():
            db.session.add(RolePermission(role_id=roles['admin'].id, permission_id=perm.id))

    manager_perms = [
        'menu.view', 'menu.manage', 'inventory.view', 'inventory.manage',
        'tables.view', 'tables.manage', 'reports.view', 'staff.manage',
        'customers.manage'
    ]
    for pslug in manager_perms:
        if not RolePermission.query.filter_by(role_id=roles['manager'].id, permission_id=perms[pslug].id).first():
            db.session.add(RolePermission(role_id=roles['manager'].id, permission_id=perms[pslug].id))

    for role_slug in ('waiter', 'cashier'):
        for permission_slug in ('orders.pos', 'orders.manage', 'billing.manage'):
            if not RolePermission.query.filter_by(
                role_id=roles[role_slug].id,
                permission_id=perms[permission_slug].id
            ).first():
                db.session.add(RolePermission(
                    role_id=roles[role_slug].id,
                    permission_id=perms[permission_slug].id
                ))

    if not RolePermission.query.filter_by(
        role_id=roles['kitchen'].id,
        permission_id=perms['kitchen.view'].id
    ).first():
        db.session.add(RolePermission(
            role_id=roles['kitchen'].id,
            permission_id=perms['kitchen.view'].id
        ))

    # ==========================================
    # 2. USERS
    # ==========================================
    users_data = [
        ('admin', 'admin@restaurant.com', 'Admin@123', 'System Administrator', '+1-555-0100', 'admin'),
        ('manager', 'manager@restaurant.com', 'Manager@123', 'Jane Miller', '+1-555-0101', 'manager'),
        ('waiter', 'waiter@restaurant.com', 'Waiter@123', 'Alex Rivera', '+1-555-0102', 'waiter'),
    ]

    users = {}
    for uname, email, pwd, fname, phone, rslug in users_data:
        user = User.query.filter_by(username=uname).first()
        if not user:
            user = User(
                username=uname,
                email=email,
                full_name=fname,
                phone=phone,
                role_id=roles[rslug].id
            )
            user.set_password(pwd)
            db.session.add(user)
            db.session.flush()
        users[uname] = user

    admin_user_id = users['admin'].id

    # ==========================================
    # 3. MENU CATEGORIES & SUBCATEGORIES
    # ==========================================
    categories_data = [
        ('Appetizers', 'appetizers', 'Fresh starters and finger foods', 1),
        ('Main Course', 'main-course', 'Hearty chef specialties, steaks, and pasta', 2),
        ('Beverages', 'beverages', 'Refreshing drinks, wines, and artisan coffees', 3),
        ('Desserts', 'desserts', 'Handcrafted pastries and sweet treats', 4),
    ]

    categories = {}
    for name, slug, desc, order in categories_data:
        cat = Category.query.filter_by(slug=slug).first()
        if not cat:
            cat = Category(
                name=name,
                slug=slug,
                description=desc,
                display_order=order,
                created_by=admin_user_id
            )
            db.session.add(cat)
            db.session.flush()
        categories[slug] = cat

    subcategories_data = [
        ('appetizers', 'Salads & Soups', 'salads-soups', 'Fresh garden salads and warm soups', 1),
        ('main-course', 'Pasta & Risotto', 'pasta-risotto', 'Traditional Italian hand-made pasta', 1),
        ('main-course', 'Signature Steaks', 'signature-steaks', 'Charbroiled USDA prime cuts', 2),
        ('beverages', 'Artisan Coffee', 'artisan-coffee', 'Single origin specialty espresso', 1),
    ]

    subcats = {}
    for cat_slug, name, slug, desc, order in subcategories_data:
        sub = SubCategory.query.filter_by(category_id=categories[cat_slug].id, slug=slug).first()
        if not sub:
            sub = SubCategory(
                category_id=categories[cat_slug].id,
                name=name,
                slug=slug,
                description=desc,
                display_order=order,
                created_by=admin_user_id
            )
            db.session.add(sub)
            db.session.flush()
        subcats[slug] = sub

    # ==========================================
    # 4. INGREDIENTS
    # ==========================================
    ingredients_data = [
        ('Arborio Rice', 'kg', 4.50, 'None'),
        ('Prime Ribeye Beef', 'kg', 28.00, 'None'),
        ('Truffle Oil', 'liter', 45.00, 'None'),
        ('Mozzarella Di Bufala', 'kg', 9.50, 'Dairy / Milk'),
        ('Espresso Blend Beans', 'kg', 22.00, 'Caffeine'),
        ('Belgian Dark Chocolate', 'kg', 16.00, 'Dairy, Soy'),
    ]

    for name, unit, cost, allergen in ingredients_data:
        if not Ingredient.query.filter_by(name=name).first():
            db.session.add(Ingredient(
                name=name,
                unit=unit,
                cost_per_unit=cost,
                allergen_info=allergen,
                created_by=admin_user_id
            ))
    db.session.flush()

    # ==========================================
    # 5. MENU ITEMS & VARIANTS
    # ==========================================
    menu_items_data = [
        ('appetizers', 'salads-soups', 'Truffle Mushroom Bruschetta', 'bruschetta', 'Toasted sourdough with wild forest mushrooms and white truffle drizzle', 12.50, 10, True, False),
        ('appetizers', None, 'Crispy Calamari Rings', 'crispy-calamari', 'Lightly breaded squid served with house remoulade and grilled lemon', 14.00, 12, False, False),
        ('main-course', 'pasta-risotto', 'Wild Mushroom Risotto', 'mushroom-risotto', 'Creamy Arborio rice with porcini mushrooms, parmesan crisp, and fresh herbs', 21.00, 20, True, False),
        ('main-course', 'signature-steaks', 'Prime Ribeye Steak 350g', 'prime-ribeye-steak', 'Grass-fed ribeye grilled with garlic rosemary butter and roasted asparagus', 38.50, 25, False, False),
        ('main-course', None, 'Artisan Margherita Pizza', 'margherita-pizza', 'San Marzano tomato sauce, fresh mozzarella, and sweet garden basil', 16.00, 15, True, False),
        ('beverages', 'artisan-coffee', 'Espresso Romano Single Origin', 'espresso-romano', 'Double shot extract with a twist of lemon peel and velvety crema', 4.50, 5, True, False),
        ('desserts', None, 'Classic Italian Tiramisu', 'classic-tiramisu', 'Espresso-soaked ladyfingers layered with whipped mascarpone cream and cocoa', 9.50, 8, True, False),
    ]

    for cat_slug, sub_slug, name, slug, desc, price, prep, veg, spicy in menu_items_data:
        item = MenuItem.query.filter_by(slug=slug).first()
        if not item:
            item = MenuItem(
                category_id=categories[cat_slug].id,
                subcategory_id=subcats[sub_slug].id if sub_slug else None,
                name=name,
                slug=slug,
                description=desc,
                base_price=price,
                prep_time_minutes=prep,
                is_vegetarian=veg,
                is_spicy=spicy,
                created_by=admin_user_id
            )
            db.session.add(item)
            db.session.flush()

            # Add variants for steak and pizza
            if slug == 'prime-ribeye-steak':
                db.session.add_all([
                    ItemVariant(menu_item_id=item.id, name='Medium Rare (Recommended)', additional_price=0.00, sku='STEAK-MR', created_by=admin_user_id),
                    ItemVariant(menu_item_id=item.id, name='Medium', additional_price=0.00, sku='STEAK-M', created_by=admin_user_id),
                    ItemVariant(menu_item_id=item.id, name='Well Done', additional_price=0.00, sku='STEAK-WD', created_by=admin_user_id),
                ])
            elif slug == 'margherita-pizza':
                db.session.add_all([
                    ItemVariant(menu_item_id=item.id, name='Regular 10"', additional_price=0.00, sku='PIZZA-REG', created_by=admin_user_id),
                    ItemVariant(menu_item_id=item.id, name='Large 14"', additional_price=4.50, sku='PIZZA-LRG', created_by=admin_user_id),
                ])
    db.session.flush()

    # ==========================================
    # 6. INVENTORY SUPPLIERS & ITEMS
    # ==========================================
    suppliers_data = [
        ('Prime Meats & Co.', 'Marco Rossi', 'orders@primemeats.com', '+1-555-0201', '104 Industrial Pkwy, Chicago, IL', 'TAX-88901'),
        ('Fresh Farm Dairy & Produce', 'Sarah Lin', 'info@freshfarm.com', '+1-555-0202', '52 Valley Road, Naperville, IL', 'TAX-44321'),
        ('Artisan Beverage Roasters', 'David Vance', 'sales@artisanbev.com', '+1-555-0203', '77 Commerce Blvd, Chicago, IL', 'TAX-11928'),
    ]

    suppliers = {}
    for name, cname, email, phone, addr, tax in suppliers_data:
        sup = Supplier.query.filter_by(name=name).first()
        if not sup:
            sup = Supplier(
                name=name,
                contact_name=cname,
                email=email,
                phone=phone,
                address=addr,
                tax_id=tax,
                created_by=admin_user_id
            )
            db.session.add(sup)
            db.session.flush()
        suppliers[name] = sup

    inventory_data = [
        ('Prime Meats & Co.', 'Ribeye Cut Beef', 'INV-BEEF-001', 'Meat', 'kg', 22.50, 10.00, 15.00, 24.00),
        ('Fresh Farm Dairy & Produce', 'Mozzarella Block', 'INV-DAIRY-002', 'Dairy', 'kg', 28.00, 8.00, 12.00, 8.50),
        ('Artisan Beverage Roasters', 'Espresso Blend Beans', 'INV-BEV-003', 'Beverages', 'kg', 14.00, 5.00, 10.00, 20.00),
        ('Fresh Farm Dairy & Produce', 'Arborio Rice Sack', 'INV-DRY-004', 'Dry Goods', 'kg', 45.00, 15.00, 25.00, 3.80),
        ('Fresh Farm Dairy & Produce', 'Extra Virgin Olive Oil', 'INV-OIL-005', 'Oils & Condiments', 'liter', 4.00, 8.00, 12.00, 14.50),
    ]

    for sname, iname, sku, cat, unit, cur_stock, min_stock, reorder_qty, unit_cost in inventory_data:
        item = InventoryItem.query.filter_by(sku=sku).first()
        if not item:
            item = InventoryItem(
                supplier_id=suppliers[sname].id,
                name=iname,
                sku=sku,
                category=cat,
                unit=unit,
                current_stock=cur_stock,
                minimum_stock=min_stock,
                reorder_quantity=reorder_qty,
                unit_cost=unit_cost,
                created_by=admin_user_id
            )
            db.session.add(item)
            db.session.flush()

            movement = StockMovement(
                inventory_item_id=item.id,
                movement_type='IN',
                quantity=cur_stock,
                unit_cost=unit_cost,
                reference_no=f'INIT-IN-{sku}',
                notes='Initial stock load',
                created_by=admin_user_id
            )
            db.session.add(movement)
    db.session.flush()

    # ==========================================
    # 7. TABLES & RESERVATIONS
    # ==========================================
    tables_data = [
        ('T-01', 2, 'Indoor', 'available'),
        ('T-02', 4, 'Indoor', 'available'),
        ('T-03', 6, 'Indoor', 'available'),
        ('T-04', 2, 'Terrace', 'available'),
        ('T-05', 4, 'Terrace', 'reserved'),
        ('VIP-01', 8, 'VIP Lounge', 'available'),
        ('BAR-01', 2, 'Bar', 'available'),
        ('BAR-02', 2, 'Bar', 'available'),
    ]

    tables = {}
    for tnum, cap, zone, stat in tables_data:
        tbl = RestaurantTable.query.filter_by(table_number=tnum).first()
        if not tbl:
            tbl = RestaurantTable(
                table_number=tnum,
                capacity=cap,
                location_zone=zone,
                table_status=stat,
                qr_code_token=f'QR-{tnum}',
                created_by=admin_user_id
            )
            db.session.add(tbl)
            db.session.flush()
        tables[tnum] = tbl

    reservations_data = [
        ('T-05', 'Eleanor Vance', '+1-555-8812', 'eleanor@example.com', 4, datetime.utcnow() + timedelta(hours=3), 'confirmed', 'Window seating preferred'),
        ('VIP-01', 'Marcus Sterling', '+1-555-7733', 'sterling@example.com', 6, datetime.utcnow() + timedelta(days=1), 'pending', 'Anniversary celebration champagne request'),
        ('T-02', 'Sophia Chen', '+1-555-9944', 'sophia@example.com', 2, datetime.utcnow() - timedelta(minutes=45), 'seated', 'Quick lunch'),
    ]

    for tnum, cname, cphone, cemail, gcount, rtime, rstat, reqs in reservations_data:
        if not Reservation.query.filter_by(customer_name=cname).first():
            res = Reservation(
                table_id=tables[tnum].id,
                customer_name=cname,
                customer_phone=cphone,
                customer_email=cemail,
                guest_count=gcount,
                reservation_time=rtime,
                reservation_status=rstat,
                special_requests=reqs,
                created_by=admin_user_id
            )
            db.session.add(res)

    # ==========================================
    # 8. PHASE 2: CUSTOMERS & ADDRESSES
    # ==========================================
    customers_data = [
        ('Emily Watson', 'emily@example.com', '+1-555-4321', 'Preferred window booth seating', '124 Oak Street', 'Chicago', 'IL', '60601'),
        ('David Miller', 'david@example.com', '+1-555-8765', 'Corporate dining account', '88 LaSalle Blvd', 'Chicago', 'IL', '60602'),
        ('Chloe Bennett', 'chloe@example.com', '+1-555-6677', 'Regular Friday dinner patron', '310 Pine Ave', 'Naperville', 'IL', '60540'),
    ]

    customers = {}
    for cname, cmail, cphone, cnotes, a1, city, state, zipc in customers_data:
        cust = Customer.query.filter_by(phone=cphone).first()
        if not cust:
            cust = Customer(
                name=cname,
                email=cmail,
                phone=cphone,
                notes=cnotes,
                created_by=admin_user_id
            )
            db.session.add(cust)
            db.session.flush()

            addr = Address(
                customer_id=cust.id,
                address_line1=a1,
                city=city,
                state=state,
                postal_code=zipc,
                address_type='Home',
                is_default=True,
                created_by=admin_user_id
            )
            db.session.add(addr)
        customers[cname] = cust
    db.session.flush()

    # ==========================================
    # 9. PHASE 2: ORDER TYPES
    # ==========================================
    order_types_data = [
        ('Dine-In', 'dine-in', 'Full table service dining in restaurant'),
        ('Takeaway', 'takeaway', 'Counter takeout pickup orders'),
        ('Delivery', 'delivery', 'Home / office courier delivery orders'),
    ]

    order_types = {}
    for name, slug, desc in order_types_data:
        ot = OrderType.query.filter_by(slug=slug).first()
        if not ot:
            ot = OrderType(name=name, slug=slug, description=desc, created_by=admin_user_id)
            db.session.add(ot)
            db.session.flush()
        order_types[slug] = ot
    db.session.flush()

    # ==========================================
    # 10. PHASE 2: PAYMENT METHODS
    # ==========================================
    pm_data = [
        ('Cash', 'cash', True, False),
        ('Credit Card', 'credit_card', False, True),
        ('Debit Card', 'debit_card', False, True),
        ('Mobile Wallet / Apple Pay', 'mobile_wallet', False, True),
    ]

    for name, slug, is_cash, is_digital in pm_data:
        if not PaymentMethod.query.filter_by(slug=slug).first():
            db.session.add(PaymentMethod(
                name=name,
                slug=slug,
                is_cash=is_cash,
                is_digital=is_digital,
                created_by=admin_user_id
            ))
    db.session.flush()

    # ==========================================
    # 11. PHASE 2: TAXES & DISCOUNTS
    # ==========================================
    taxes_data = [
        ('Sales Tax (State & City)', 'ST', 8.25, False),
        ('Service Charge', 'SC', 5.00, False),
    ]

    for name, code, rate, is_inc in taxes_data:
        if not Tax.query.filter_by(code=code).first():
            db.session.add(Tax(
                name=name,
                code=code,
                rate_percentage=rate,
                is_inclusive=is_inc,
                created_by=admin_user_id
            ))

    discounts_data = [
        ('Happy Hour 15%', 'percentage', 15.00),
        ('Senior Citizen 10%', 'percentage', 10.00),
    ]

    for name, dtype, rate in discounts_data:
        if not Discount.query.filter_by(name=name).first():
            db.session.add(Discount(
                name=name,
                discount_type=dtype,
                rate=rate,
                created_by=admin_user_id
            ))
    db.session.flush()

    # ==========================================
    # 12. PHASE 2: SAMPLE COUPONS
    # ==========================================
    now = datetime.utcnow()
    coupons_data = [
        ('WELCOME10', 'percentage', 10.00, 20.00, 500, now - timedelta(days=1), now + timedelta(days=365)),
        ('FLAT5', 'fixed_amount', 5.00, 25.00, 200, now - timedelta(days=1), now + timedelta(days=365)),
    ]

    for code, dtype, dval, min_spend, max_u, vfrom, vuntil in coupons_data:
        if not Coupon.query.filter_by(code=code).first():
            db.session.add(Coupon(
                code=code,
                discount_type=dtype,
                discount_value=dval,
                min_order_amount=min_spend,
                max_uses=max_u,
                valid_from=vfrom,
                valid_until=vuntil,
                created_by=admin_user_id
            ))
    db.session.commit()

    # ==========================================
    # 13. PHASE 2: SAMPLE ACTIVE ORDER & INVOICE
    # ==========================================
    from app.models.orders import Order
    if Order.query.count() == 0:
        bruschetta = MenuItem.query.filter_by(slug='bruschetta').first()
        steak = MenuItem.query.filter_by(slug='prime-ribeye-steak').first()
        t2 = RestaurantTable.query.filter_by(table_number='T-02').first()
        cust = Customer.query.first()

        if bruschetta and steak and t2:
            OrderService.place_order(
                order_type_slug='dine-in',
                items_data=[
                    {'menu_item_id': bruschetta.id, 'quantity': 2, 'instructions': 'Extra crispy toasted sourdough'},
                    {'menu_item_id': steak.id, 'quantity': 1, 'instructions': 'Medium rare please'}
                ],
                table_id=t2.id,
                customer_id=cust.id if cust else None,
                user_id=admin_user_id,
                special_notes='VIP patron anniversary celebration table.',
                coupon_code='WELCOME10'
            )
            print("Sample active order, kitchen ticket, and invoice generated!")

    # ==========================================
    # 14. PHASE 3: DEPARTMENTS, SHIFTS & EMPLOYEES
    # ==========================================
    dept_data = [
        ('Kitchen Operations', 'Culinary preparation, chefs, line cooks, dishwashing'),
        ('Front of House', 'Host, waiters, sommeliers, table service'),
        ('Delivery & Logistics', 'Dispatch and courier fleet operations'),
        ('Management', 'Store managers, supervisors, accounting'),
    ]
    depts = {}
    for name, desc in dept_data:
        dept = Department.query.filter_by(name=name).first()
        if not dept:
            dept = Department(name=name, description=desc, created_by=admin_user_id)
            db.session.add(dept)
            db.session.flush()
        depts[name] = dept

    shifts_data = [
        ('Morning Shift', time(8, 0), time(16, 0), 'Breakfast & Lunch service'),
        ('Evening Shift', time(16, 0), time(0, 0), 'Dinner service & Closing'),
    ]
    shifts = {}
    for name, st, et, desc in shifts_data:
        shift = Shift.query.filter_by(name=name).first()
        if not shift:
            shift = Shift(name=name, start_time=st, end_time=et, description=desc, created_by=admin_user_id)
            db.session.add(shift)
            db.session.flush()
        shifts[name] = shift

    emp_data = [
        ('EMP-001', 'Marco', 'Pierre', 'Executive Chef', 'Kitchen Operations', 4500.00, '+1-555-0201'),
        ('EMP-002', 'Elena', 'Rostova', 'Head Waitress', 'Front of House', 3200.00, '+1-555-0202'),
        ('EMP-003', 'David', 'Miller', 'Lead Courier', 'Delivery & Logistics', 2800.00, '+1-555-0203'),
    ]
    employees = {}
    for code, fn, ln, desig, dname, salary, phone in emp_data:
        emp = Employee.query.filter_by(employee_code=code).first()
        if not emp:
            emp = Employee(
                employee_code=code,
                first_name=fn,
                last_name=ln,
                designation=desig,
                department_id=depts[dname].id,
                shift_id=shifts['Evening Shift' if code == 'EMP-002' else 'Morning Shift'].id,
                base_salary=salary,
                emergency_contact=phone,
                hire_date=date.today() - timedelta(days=180),
                created_by=admin_user_id
            )
            db.session.add(emp)
            db.session.flush()
        elif not emp.shift_id:
            emp.shift_id = shifts['Evening Shift' if code == 'EMP-002' else 'Morning Shift'].id
        employees[code] = emp

    # Sample Attendance for today
    today = date.today()
    if not Attendance.query.filter_by(date=today).first():
        db.session.add(Attendance(
            employee_id=employees['EMP-001'].id,
            shift_id=shifts['Morning Shift'].id,
            date=today,
            clock_in=datetime.utcnow() - timedelta(hours=4),
            attendance_status='present',
            notes='On duty in kitchen prep',
            created_by=admin_user_id
        ))
        db.session.add(Attendance(
            employee_id=employees['EMP-002'].id,
            shift_id=shifts['Morning Shift'].id,
            date=today,
            clock_in=datetime.utcnow() - timedelta(hours=3, minutes=45),
            attendance_status='present',
            notes='Floor service station 1',
            created_by=admin_user_id
        ))

    # ==========================================
    # 15. PHASE 3: DELIVERY FLEET
    # ==========================================
    agent_data = [
        ('David Miller', 'bike', 'NY-DLV-101', '+1-555-0901', True, employees['EMP-003'].id),
        ('Sam Wilson', 'scooter', 'NY-DLV-102', '+1-555-0902', True, None),
    ]
    for name, vtype, plate, phone, avail, empid in agent_data:
        if not DeliveryAgent.query.filter_by(phone=phone).first():
            db.session.add(DeliveryAgent(
                name=name,
                vehicle_type=vtype,
                license_plate=plate,
                phone=phone,
                is_available=avail,
                employee_id=empid,
                created_by=admin_user_id
            ))
    db.session.flush()

    # ==========================================
    # 16. PHASE 3: EXPENSES & CATEGORIES
    # ==========================================
    exp_cat_data = [
        ('Utilities', 'Electricity, water, gas, sanitation'),
        ('Food & Beverage Supplies', 'Direct ingredient and pantry replenishment'),
        ('Rent & Facilities', 'Commercial property lease and building maintenance'),
        ('Marketing & Promotions', 'Social media ads, print promos, influencer events'),
    ]
    exp_cats = {}
    for name, desc in exp_cat_data:
        cat = ExpenseCategory.query.filter_by(name=name).first()
        if not cat:
            cat = ExpenseCategory(name=name, description=desc, created_by=admin_user_id)
            db.session.add(cat)
            db.session.flush()
        exp_cats[name] = cat

    if Expense.query.count() == 0:
        db.session.add(Expense(
            category_id=exp_cats['Utilities'].id,
            title='Monthly Electricity & Gas Utility Bill',
            amount=850.00,
            expense_date=date.today() - timedelta(days=5),
            receipt_reference='UTIL-2026-001',
            notes='Paid via bank transfer',
            approved_by_user_id=admin_user_id,
            created_by=admin_user_id
        ))
        db.session.add(Expense(
            category_id=exp_cats['Food & Beverage Supplies'].id,
            title='Organic Prime Meat & Produce Replenishment',
            amount=1240.50,
            expense_date=date.today() - timedelta(days=2),
            receipt_reference='PROD-2026-089',
            notes='Wholesale direct farm purchase',
            approved_by_user_id=admin_user_id,
            created_by=admin_user_id
        ))

    # ==========================================
    # 17. PHASE 3: LOYALTY TIERS & REWARDS
    # ==========================================
    loyalty_tiers = [
        ('Bronze', 0.00, 1.00, 0.0100, 'Basic membership, 1 point per $1 spent'),
        ('Silver', 500.00, 1.25, 0.0125, '1.25x points + priority reservations'),
        ('Gold', 1500.00, 1.50, 0.0150, '1.5x points + complimentary dessert on visits'),
        ('Platinum', 3000.00, 2.00, 0.0200, '2x points + VIP table guarantee + chef greetings'),
    ]
    for tname, min_sp, p_dol, d_pt, perks in loyalty_tiers:
        if not LoyaltyProgram.query.filter_by(tier_name=tname).first():
            db.session.add(LoyaltyProgram(
                tier_name=tname,
                min_spend=min_sp,
                points_per_dollar=p_dol,
                discount_per_point=d_pt,
                perks_description=perks,
                created_by=admin_user_id
            ))

    rewards_data = [
        ('$10 Dining Credit Voucher', 250, 'discount_voucher', 10.00),
        ('Artisan Chef Dessert', 350, 'free_item', 14.00),
        ('$25 Premium Tasting Voucher', 600, 'discount_voucher', 25.00),
    ]
    for rtitle, req_pts, rtype, rval in rewards_data:
        if not Reward.query.filter_by(title=rtitle).first():
            db.session.add(Reward(
                title=rtitle,
                points_required=req_pts,
                reward_type=rtype,
                reward_value=rval,
                is_active=True,
                created_by=admin_user_id
            ))

    # ==========================================
    # 18. PHASE 3: CUSTOMER FEEDBACK
    # ==========================================
    if CustomerFeedback.query.count() == 0:
        c1 = Customer.query.first()
        db.session.add(CustomerFeedback(
            customer_id=c1.id if c1 else None,
            food_rating=5,
            service_rating=5,
            ambience_rating=4,
            overall_rating=4.67,
            comments='The Truffle Bruschetta and Prime Ribeye Steak were world class. Excellent wine pairings!',
            response_notes='Thank you for dining with us! We look forward to hosting you again soon.',
            is_published=True,
            created_by=admin_user_id
        ))

    # ==========================================
    # 19. PHASE 3: SYSTEM SETTINGS & AUDIT LOG
    # ==========================================
    settings_data = [
        ('restaurant_name', 'GourmetOS Bistro & Lounge', 'string', 'Official restaurant business name', True),
        ('currency', 'USD', 'string', 'Base financial currency symbol', True),
        ('tax_rate_percent', '8.25', 'number', 'Standard state & city tax rate', True),
        ('service_charge_percent', '5.00', 'number', 'Default dine-in service charge', True),
        ('operating_hours', '11:00 AM - 11:00 PM', 'string', 'Restaurant floor operational schedule', True),
        ('contact_email', 'concierge@gourmetos.com', 'string', 'General inquiries and bookings contact', True),
    ]
    for key, val, stype, desc, is_pub in settings_data:
        if not SystemSetting.query.filter_by(setting_key=key).first():
            db.session.add(SystemSetting(
                setting_key=key,
                setting_value=val,
                setting_type=stype,
                description=desc,
                is_public=is_pub,
                created_by=admin_user_id
            ))

    if AuditLog.query.count() == 0:
        db.session.add(AuditLog(
            user_id=admin_user_id,
            action='SYSTEM_BOOT',
            target_entity='SystemSetting',
            details_json='{"message": "Restaurant Management System initialized with 44 relational models"}',
            ip_address='127.0.0.1',
            created_by=admin_user_id
        ))

    if not Notification.query.filter_by(user_id=admin_user_id).first():
        db.session.add(Notification(
            user_id=admin_user_id,
            title='Welcome to notifications',
            message='New orders, low inventory, and received payments will appear here.',
            notification_type='system',
            link='/notifications/',
            created_by=admin_user_id
        ))

    db.session.commit()
    print("All Phase 1, Phase 2, and Phase 3 database seeding completed successfully!")


if __name__ == '__main__':
    from app import create_app
    app = create_app()
    with app.app_context():
        seed_database()
