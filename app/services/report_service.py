from datetime import date, datetime, time, timedelta
from decimal import Decimal
from sqlalchemy import func
from app.extensions import db
from app.services.cache_service import cache
from app.models.billing import Invoice, Payment, PaymentMethod
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
                func.sum(OrderItem.total_price).label('total_sales')
            )
            .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
            .join(Order, Order.id == OrderItem.order_id)
            .filter(Order.order_status != 'cancelled')
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
    def get_dashboard_chart_data(force_refresh=False, today=None):
        """Return cached chart series for dashboard sales and order activity."""
        today = today or date.today()
        cache_key = f'reports:dashboard_charts:{today.isoformat()}'
        if not force_refresh:
            cached = cache.get(cache_key)
            if cached:
                return cached

        first_day = today - timedelta(days=6)
        start = datetime.combine(first_day, time.min)
        end = datetime.combine(today + timedelta(days=1), time.min)
        payments = (
            Payment.query.join(Payment.invoice)
            .filter(
                Payment.payment_status == 'completed',
                Payment.payment_date >= start,
                Payment.payment_date < end
            )
            .order_by(Payment.payment_date.asc())
            .all()
        )
        sales_by_day = {first_day + timedelta(days=offset): Decimal('0.00') for offset in range(7)}
        for payment in payments:
            payment_day = payment.payment_date.date()
            sales_by_day[payment_day] += Decimal(str(payment.amount))

        order_status_rows = (
            db.session.query(Order.order_status, func.count(Order.id))
            .group_by(Order.order_status)
            .order_by(Order.order_status.asc())
            .all()
        )
        payment_method_rows = (
            db.session.query(
                PaymentMethod.name,
                func.coalesce(func.sum(Payment.amount), Decimal('0.00'))
            )
            .join(Payment, Payment.payment_method_id == PaymentMethod.id)
            .filter(Payment.payment_status == 'completed')
            .group_by(PaymentMethod.name)
            .order_by(PaymentMethod.name.asc())
            .all()
        )

        top_items = ReportService.get_top_selling_items(limit=5)
        result = {
            'sales_last_7_days': {
                'labels': [day.strftime('%b %d') for day in sales_by_day],
                'values': [float(amount) for amount in sales_by_day.values()],
            },
            'orders_by_status': {
                'labels': [row[0].replace('_', ' ').title() for row in order_status_rows],
                'values': [int(row[1]) for row in order_status_rows],
            },
            'top_selling_items': {
                'labels': [row['name'] for row in top_items],
                'values': [row['qty_sold'] for row in top_items],
            },
            'revenue_by_payment_method': {
                'labels': [row[0] for row in payment_method_rows],
                'values': [float(row[1] or 0) for row in payment_method_rows],
            },
        }
        cache.set(cache_key, result, timeout=120)
        return result

    @staticmethod
    def get_sales_expense_report(start_date, end_date, force_refresh=False):
        """Return daily and monthly paid sales/expense totals for an inclusive date range."""
        if end_date < start_date:
            raise ValueError('The report end date must be on or after the start date.')

        cache_key = f'reports:sales_expenses:{start_date.isoformat()}:{end_date.isoformat()}'
        if not force_refresh:
            cached = cache.get(cache_key)
            if cached:
                return cached

        sales = (
            Payment.query.join(Payment.invoice)
            .filter(
                Payment.payment_status == 'completed',
                Payment.payment_date >= datetime.combine(start_date, time.min),
                Payment.payment_date < datetime.combine(end_date + timedelta(days=1), time.min)
            )
            .order_by(Payment.payment_date.asc())
            .all()
        )
        expenses = (
            Expense.query.filter(
                Expense.expense_date >= start_date,
                Expense.expense_date <= end_date
            )
            .order_by(Expense.expense_date.asc())
            .all()
        )

        sales_by_day = {}
        expenses_by_day = {}
        for payment in sales:
            key = payment.payment_date.date().isoformat()
            sales_by_day[key] = sales_by_day.get(key, Decimal('0.00')) + Decimal(str(payment.amount))
        for expense in expenses:
            key = expense.expense_date.isoformat()
            expenses_by_day[key] = expenses_by_day.get(key, Decimal('0.00')) + Decimal(str(expense.amount))

        daily = []
        monthly_totals = {}
        current_day = start_date
        while current_day <= end_date:
            key = current_day.isoformat()
            sales_total = sales_by_day.get(key, Decimal('0.00'))
            expense_total = expenses_by_day.get(key, Decimal('0.00'))
            daily.append({
                'date': key,
                'sales': float(sales_total),
                'expenses': float(expense_total),
            })
            month_key = current_day.strftime('%Y-%m')
            month = monthly_totals.setdefault(month_key, {
                'month': month_key,
                'sales': Decimal('0.00'),
                'expenses': Decimal('0.00')
            })
            month['sales'] += sales_total
            month['expenses'] += expense_total
            current_day += timedelta(days=1)

        result = {
            'daily': daily,
            'monthly': [
                {
                    'month': row['month'],
                    'sales': float(row['sales']),
                    'expenses': float(row['expenses'])
                }
                for row in monthly_totals.values()
            ],
        }
        cache.set(cache_key, result, timeout=120)
        return result

    @staticmethod
    def get_sales_export_rows(start_date, end_date):
        """Return completed payment rows for CSV export using ORM queries."""
        payments = (
            Payment.query.join(Payment.invoice)
            .join(Invoice.order)
            .outerjoin(Payment.payment_method)
            .filter(
                Payment.payment_status == 'completed',
                Payment.payment_date >= datetime.combine(start_date, time.min),
                Payment.payment_date < datetime.combine(end_date + timedelta(days=1), time.min)
            )
            .order_by(Payment.payment_date.asc(), Payment.id.asc())
            .all()
        )
        return [
            [
                payment.payment_date.isoformat(),
                payment.transaction_reference,
                payment.invoice.invoice_number,
                payment.invoice.order.order_number if payment.invoice.order else '',
                payment.payment_method.name if payment.payment_method else '',
                str(payment.amount),
            ]
            for payment in payments
        ]

    @staticmethod
    def get_expense_export_rows(start_date, end_date):
        """Return expense rows for CSV export using ORM queries."""
        expenses = (
            Expense.query.filter(
                Expense.expense_date >= start_date,
                Expense.expense_date <= end_date
            )
            .order_by(Expense.expense_date.asc(), Expense.id.asc())
            .all()
        )
        return [
            [
                expense.expense_date.isoformat(),
                expense.title,
                expense.category.name if expense.category else '',
                str(expense.amount),
                expense.payment_method.name if expense.payment_method else '',
                expense.receipt_reference or '',
            ]
            for expense in expenses
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
