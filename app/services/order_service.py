import uuid
from datetime import datetime
from decimal import Decimal
from app.extensions import db
from app.models.orders import Order, OrderItem, OrderType, OrderStatusHistory
from app.models.kitchen import KitchenTicket
from app.models.tables import RestaurantTable
from app.models.menu import MenuItem, ItemVariant
from app.models.inventory import InventoryItem, StockMovement
from app.services.billing_service import BillingService
from app.services.cache_service import cache


class OrderError(Exception):
    """Base exception for order operations."""
    pass


class OrderPlacementError(OrderError):
    """Raised when placing an order fails."""
    pass


class OrderStatusError(OrderError):
    """Raised when an order status transition fails."""
    pass


class OrderCancellationError(OrderError):
    """Raised when an order cancellation fails."""
    pass


class OrderService:
    """Business logic for Order lifecycle, Kitchen integration, and Inventory coordination."""

    VALID_TRANSITIONS = {
        'pending': ['confirmed', 'preparing', 'cancelled'],
        'confirmed': ['preparing', 'cancelled'],
        'preparing': ['ready', 'cancelled'],
        'ready': ['served', 'completed', 'cancelled'],
        'served': ['completed', 'cancelled'],
        'completed': [],
        'cancelled': []
    }

    @staticmethod
    def place_order(order_type_slug, items_data, table_id=None, customer_id=None, user_id=None, special_notes=None, coupon_code=None, simulate_failure=False):
        """
        ATOMIC TRANSACTION (Place Order):
        1. Create Order header
        2. Create OrderItems and calculate totals
        3. Create KitchenTicket for kitchen display
        4. Mark RestaurantTable as occupied (if Dine-in)
        5. Deduct Inventory items and record StockMovement (movement_type='OUT')
        6. Automatically generate draft Invoice
        7. Commits atomically. If any step fails, rolls back all changes completely.
        """
        try:
            # 1. Validate Order Type
            order_type = OrderType.query.filter_by(slug=order_type_slug, status='active', is_deleted=False).first()
            if not order_type:
                raise OrderPlacementError(f"Invalid order type: '{order_type_slug}'.")

            if not items_data or len(items_data) == 0:
                raise OrderPlacementError("An order must contain at least one item.")

            # Generate unique human-readable order number
            timestamp_str = datetime.utcnow().strftime('%Y%m%d')
            unique_seq = uuid.uuid4().hex[:6].upper()
            order_num = f"ORD-{timestamp_str}-{unique_seq}"

            # 2. Table handling & status update
            table = None
            if table_id:
                table = RestaurantTable.query.filter_by(id=table_id, is_deleted=False).first()
                if not table:
                    raise OrderPlacementError(f"Table #{table_id} does not exist.")
                if order_type.slug == 'dine-in':
                    table.table_status = 'occupied'

            order = Order(
                order_number=order_num,
                order_type_id=order_type.id,
                table_id=table.id if table else None,
                customer_id=customer_id,
                user_id=user_id or 1,
                order_status='pending',
                special_notes=special_notes
            )
            db.session.add(order)
            db.session.flush()  # Populates order.id for relations

            # 3. Process Order Items & Deduct Inventory
            total_amount = Decimal('0.00')

            for item_input in items_data:
                menu_item_id = item_input.get('menu_item_id')
                qty = int(item_input.get('quantity', 1))
                variant_id = item_input.get('variant_id')
                notes = item_input.get('instructions')

                if qty <= 0:
                    raise OrderPlacementError("Item quantity must be at least 1.")

                menu_item = MenuItem.query.filter_by(id=menu_item_id, is_deleted=False).first()
                if not menu_item:
                    raise OrderPlacementError(f"Menu item #{menu_item_id} not found.")

                unit_price = Decimal(str(menu_item.base_price))

                if variant_id:
                    variant = ItemVariant.query.filter_by(id=variant_id, menu_item_id=menu_item.id, is_deleted=False).first()
                    if variant:
                        unit_price += Decimal(str(variant.additional_price))

                item_total = unit_price * Decimal(str(qty))
                total_amount += item_total

                order_item = OrderItem(
                    order_id=order.id,
                    menu_item_id=menu_item.id,
                    item_variant_id=variant_id,
                    quantity=qty,
                    unit_price=unit_price,
                    total_price=item_total,
                    special_instructions=notes,
                    item_status='pending'
                )
                db.session.add(order_item)

                # Deduct inventory stock for raw supplies matching the dish/category
                # Match inventory item by item name prefix or SKU
                inv_item = InventoryItem.query.filter(
                    (InventoryItem.name.ilike(f"%{menu_item.name[:8]}%")) |
                    (InventoryItem.category.ilike(f"%{menu_item.category.name if menu_item.category else ''}%"))
                ).first()

                if not inv_item:
                    # Fallback to general inventory item to track stock consumption
                    inv_item = InventoryItem.query.first()

                if inv_item:
                    deduct_qty = Decimal(str(qty))
                    inv_item.current_stock = Decimal(str(inv_item.current_stock)) - deduct_qty

                    movement = StockMovement(
                        inventory_item_id=inv_item.id,
                        movement_type='OUT',
                        quantity=deduct_qty,
                        unit_cost=inv_item.unit_cost,
                        reference_no=order_num,
                        notes=f"Stock deduction for {qty}x {menu_item.name} on order {order_num}",
                        created_by=user_id
                    )
                    db.session.add(movement)

            order.total_amount = total_amount

            # 4. Generate Kitchen Ticket
            ticket_seq = uuid.uuid4().hex[:4].upper()
            kitchen_ticket = KitchenTicket(
                ticket_number=f"KKT-{timestamp_str}-{ticket_seq}",
                order_id=order.id,
                kitchen_status='pending',
                priority='normal',
                notes=special_notes,
                created_by=user_id
            )
            db.session.add(kitchen_ticket)

            # 5. Record initial status history
            history = OrderStatusHistory(
                order_id=order.id,
                from_status=None,
                to_status='pending',
                changed_by_user_id=user_id,
                notes='Order created and sent to kitchen via POS.'
            )
            db.session.add(history)

            # 6. Auto-generate draft Invoice
            BillingService.create_or_update_invoice(
                order,
                coupon_code=coupon_code,
                user_id=user_id
            )

            # Forced failure injection for rollback testing
            if simulate_failure:
                raise OrderPlacementError("Simulated failure during place_order transaction for test verification.")

            # --- COMMIT POINT ---
            # All operations (Order, OrderItems, KitchenTicket, Table occupancy, Inventory deductions, Invoice)
            # are committed to the database in a single atomic operation.
            db.session.commit()

            # Invalidate caches
            cache.delete_pattern("dashboard:*")
            cache.delete_pattern("reports:*")
            return order

        except Exception as e:
            # --- ROLLBACK POINT ---
            # If any step fails, all operations are reverted immediately.
            # Table status remains unchanged, stock deductions undone, no orphan orders.
            db.session.rollback()
            raise OrderPlacementError(str(e))

    @staticmethod
    def update_order_status(order_id, new_status, user_id=None, notes=None):
        """
        Transition order status with state-machine validation and history audit.
        """
        try:
            order = Order.query.filter_by(id=order_id, is_deleted=False).first()
            if not order:
                raise OrderStatusError(f"Order #{order_id} not found.")

            current = order.order_status
            allowed = OrderService.VALID_TRANSITIONS.get(current, [])
            if new_status not in allowed and new_status != current:
                raise OrderStatusError(f"Invalid status transition from '{current}' to '{new_status}'.")

            order.order_status = new_status

            # Synchronize kitchen ticket status
            if order.kitchen_ticket:
                kt = order.kitchen_ticket
                if new_status == 'preparing':
                    kt.mark_preparing()
                elif new_status == 'ready':
                    kt.mark_ready()
                elif new_status == 'served':
                    kt.mark_served()
                elif new_status == 'cancelled':
                    kt.kitchen_status = 'cancelled'

            # Log to OrderStatusHistory
            history = OrderStatusHistory(
                order_id=order.id,
                from_status=current,
                to_status=new_status,
                changed_by_user_id=user_id,
                notes=notes
            )
            db.session.add(history)

            # --- COMMIT POINT ---
            db.session.commit()
            cache.delete_pattern("dashboard:*")
            return order

        except Exception as e:
            # --- ROLLBACK POINT ---
            db.session.rollback()
            raise OrderStatusError(str(e))

    @staticmethod
    def cancel_order(order_id, user_id=None, reason=None, simulate_failure=False):
        """
        ATOMIC TRANSACTION (Cancel Order):
        1. Validate order can be cancelled (not already completed or cancelled)
        2. Set order status to 'cancelled'
        3. Restore inventory via reverse StockMovements (movement_type='IN')
        4. Free assigned restaurant table back to 'available'
        5. Mark invoice and associated payments as 'void'
        6. Cancel kitchen ticket
        7. Commits atomically. If any error occurs, rolls back completely.
        """
        try:
            order = Order.query.filter_by(id=order_id, is_deleted=False).first()
            if not order:
                raise OrderCancellationError(f"Order #{order_id} not found.")

            if order.order_status in ['completed', 'cancelled']:
                raise OrderCancellationError(f"Order #{order_id} cannot be cancelled as it is already '{order.order_status}'.")

            old_status = order.order_status
            order.order_status = 'cancelled'

            # 1. Update Kitchen ticket
            if order.kitchen_ticket:
                order.kitchen_ticket.kitchen_status = 'cancelled'

            # 2. Release Table
            if order.table:
                order.table.table_status = 'available'

            # 3. Restore inventory stock
            out_movements = StockMovement.query.filter_by(
                reference_no=order.order_number,
                movement_type='OUT',
                is_deleted=False
            ).all()

            for movement in out_movements:
                item = movement.inventory_item
                if item:
                    item.current_stock = Decimal(str(item.current_stock)) + Decimal(str(movement.quantity))

                    reverse_mov = StockMovement(
                        inventory_item_id=item.id,
                        movement_type='IN',
                        quantity=movement.quantity,
                        unit_cost=movement.unit_cost,
                        reference_no=f"REV-{order.order_number}",
                        notes=f"Reversed stock deduction for cancelled order {order.order_number}",
                        created_by=user_id
                    )
                    db.session.add(reverse_mov)

            # 4. Void Invoice and Payments
            if order.invoice:
                order.invoice.payment_status = 'void'
                for payment in order.invoice.payments:
                    payment.payment_status = 'void'

            # 5. Log audit history
            history = OrderStatusHistory(
                order_id=order.id,
                from_status=old_status,
                to_status='cancelled',
                changed_by_user_id=user_id,
                notes=reason or 'Order cancelled by user/manager.'
            )
            db.session.add(history)

            # Forced failure injection for rollback testing
            if simulate_failure:
                raise OrderCancellationError("Simulated failure during cancel_order transaction for test verification.")

            # --- COMMIT POINT ---
            # All changes (Order cancelled, Table freed, Inventory restored, Invoice voided) committed atomically
            db.session.commit()
            cache.delete_pattern("dashboard:*")
            cache.delete_pattern("reports:*")
            return order

        except Exception as e:
            # --- ROLLBACK POINT ---
            # All changes reverted on failure
            db.session.rollback()
            raise OrderCancellationError(str(e))
