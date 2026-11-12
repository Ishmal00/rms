from app.models.base import BaseModel, register_base_model_events
from app.models.auth import Role, Permission, RolePermission, User
from app.models.menu import Category, SubCategory, MenuItem, ItemVariant, Ingredient
from app.models.inventory import Supplier, InventoryItem, StockMovement
from app.models.tables import RestaurantTable, Reservation
from app.models.customers import Customer, Address
from app.models.orders import OrderType, Order, OrderItem, OrderStatusHistory
from app.models.kitchen import KitchenTicket
from app.models.billing import Tax, Discount, Coupon, Invoice, InvoiceItem, PaymentMethod, Payment
from app.models.staff import Department, Employee, Shift, Attendance, Payroll
from app.models.delivery import DeliveryAgent, Delivery, DeliveryTracking
from app.models.expenses import ExpenseCategory, Expense
from app.models.loyalty import LoyaltyProgram, LoyaltyTransaction, Reward
from app.models.feedback import CustomerFeedback
from app.models.settings import SystemSetting, AuditLog

__all__ = [
    # Base
    'BaseModel',
    'register_base_model_events',
    # Auth (4)
    'Role',
    'Permission',
    'RolePermission',
    'User',
    # Menu (5)
    'Category',
    'SubCategory',
    'MenuItem',
    'ItemVariant',
    'Ingredient',
    # Inventory (3)
    'Supplier',
    'InventoryItem',
    'StockMovement',
    # Tables (2)
    'RestaurantTable',
    'Reservation',
    # Customers (2)
    'Customer',
    'Address',
    # Orders (4)
    'OrderType',
    'Order',
    'OrderItem',
    'OrderStatusHistory',
    # Kitchen (1)
    'KitchenTicket',
    # Billing (7)
    'Tax',
    'Discount',
    'Coupon',
    'Invoice',
    'InvoiceItem',
    'PaymentMethod',
    'Payment',
    # Staff (5)
    'Department',
    'Employee',
    'Shift',
    'Attendance',
    'Payroll',
    # Delivery (3)
    'DeliveryAgent',
    'Delivery',
    'DeliveryTracking',
    # Expenses (2)
    'ExpenseCategory',
    'Expense',
    # Loyalty (3)
    'LoyaltyProgram',
    'LoyaltyTransaction',
    'Reward',
    # Feedback (1)
    'CustomerFeedback',
    # Settings & Audit (2)
    'SystemSetting',
    'AuditLog',
]
