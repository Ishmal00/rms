from decimal import Decimal
from sqlalchemy import func
from app.extensions import db
from app.services.cache_service import cache
from app.models.billing import Invoice
from app.models.expenses import Expense
from app.models.orders import Order, OrderItem, OrderType
from app.models.menu import MenuItem


class ReportService:
    @staticmethod
    def get_financial_kpis(force_refresh=False):
        """
        Calculates high-level financial metrics:
        Total Revenue, Total Expenses, Net Margin, Orders count, Average Ticket Size.
        Cached in Redis with in-memory fallback (TTL: 120s).
        """
        cache_key = 'reports:financial_kpis'
        if not force_refresh:
            cached = cache.get(cache_key)
            if cached:
                return {
                    'total_revenue': Decimal(str(cached.get('total_revenue', '0.00'))),
                    'total_expenses': Decimal(str(cached.get('total_expenses', '0.00'))),
                    'net_profit': Decimal(str(cached.get('net_profit', '0.00'))),
                    'margin_percent': Decimal(str(cached.get('margin_percent', '0.00'))),
                    'total_orders': cached.get('total_orders', 0),
                    'avg_ticket': Decimal(str(cached.get('avg_ticket', '0.00'))),
                }

        # 1. Revenue: sum of paid_amount on invoices
        total_revenue = db.session.query(
            func.coalesce(func.sum(Invoice.paid_amount), Decimal('0.00'))
        ).scalar() or Decimal('0.00')

        # 2. Expenses: sum of amount on expenses
        total_expenses = db.session.query(
            func.coalesce(func.sum(Expense.amount), Decimal('0.00'))
        ).scalar() or Decimal('0.00')

        # 3. Net Profit & Margin
        net_profit = total_revenue - total_expenses
        margin_percent = Decimal('0.00')
        if total_revenue > Decimal('0.00'):
            margin_percent = ((net_profit / total_revenue) * Decimal('100')).quantize(Decimal('0.01'))

        # 4. Total orders and average ticket
        total_orders = Order.query.count()
        avg_ticket = Decimal('0.00')
        if total_orders > 0 and total_revenue > Decimal('0.00'):
            avg_ticket = (total_revenue / Decimal(str(total_orders))).quantize(Decimal('0.01'))

        result = {
            'total_revenue': Decimal(str(total_revenue)),
            'total_expenses': Decimal(str(total_expenses)),
            'net_profit': Decimal(str(net_profit)),
            'margin_percent': margin_percent,
            'total_orders': total_orders,
            'avg_ticket': avg_ticket,
        }

        # Cache serializable dictionary
        cache.set(cache_key, {
            'total_revenue': str(result['total_revenue']),
            'total_expenses': str(result['total_expenses']),
            'net_profit': str(result['net_profit']),
            'margin_percent': str(result['margin_percent']),
            'total_orders': result['total_orders'],
            'avg_ticket': str(result['avg_ticket']),
        }, timeout=120)

        return result

    @staticmethod
    def get_top_selling_items(limit=5):
        """Returns top N selling items by total quantity sold."""
        results = (
            db.session.query(
                MenuItem.name,
                func.sum(OrderItem.quantity).label('qty_sold'),
                func.sum(OrderItem.subtotal).label('total_sales')
            )
            .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
            .group_by(MenuItem.name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
            .all()
        )
        return [
            {
                'name': r[0],
                'qty_sold': int(r[1] or 0),
                'total_sales': Decimal(str(r[2] or 0)).quantize(Decimal('0.01'))
            }
            for r in results
        ]

    @staticmethod
    def get_order_breakdown_by_type():
        """Returns order count and revenue grouped by order type."""
        results = (
            db.session.query(
                OrderType.name,
                func.count(Order.id).label('order_count'),
                func.coalesce(func.sum(Order.total_amount), Decimal('0.00')).label('total_volume')
            )
            .join(Order, Order.order_type_id == OrderType.id)
            .group_by(OrderType.name)
            .all()
        )
        return [
            {
                'order_type': r[0],
                'count': int(r[1] or 0),
                'total': Decimal(str(r[2] or 0)).quantize(Decimal('0.01'))
            }
            for r in results
        ]
