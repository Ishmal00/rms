from datetime import datetime, date
from flask import Blueprint, render_template
from flask_login import login_required
from app.models.menu import MenuItem, Category
from app.models.tables import RestaurantTable, Reservation
from app.models.inventory import InventoryItem
from app.services.cache_service import cache
from app.services.report_service import ReportService

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
@login_required
def index():
    # Attempt to retrieve cached stats for fast response
    stats = cache.get('dashboard:stats')

    if not stats:
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_end = datetime.combine(date.today(), datetime.max.time())

        total_menu_items = MenuItem.query.filter_by(status='active').count()
        total_categories = Category.query.filter_by(status='active').count()
        total_tables = RestaurantTable.query.count()
        available_tables = RestaurantTable.query.filter_by(table_status='available').count()
        today_reservations = Reservation.query.filter(
            Reservation.reservation_time.between(today_start, today_end)
        ).count()

        low_stock_count = InventoryItem.query.filter(
            InventoryItem.current_stock <= InventoryItem.minimum_stock
        ).count()

        stats = {
            'total_menu_items': total_menu_items,
            'total_categories': total_categories,
            'total_tables': total_tables,
            'available_tables': available_tables,
            'today_reservations': today_reservations,
            'low_stock_count': low_stock_count,
        }
        # Cache for 60 seconds
        cache.set('dashboard:stats', stats, timeout=60)

    # Fetch recent items for preview
    recent_reservations = Reservation.query.order_by(
        Reservation.reservation_time.asc()
    ).limit(5).all()

    tables_overview = RestaurantTable.query.order_by(RestaurantTable.table_number.asc()).limit(8).all()
    chart_data = ReportService.get_dashboard_chart_data()

    return render_template(
        'dashboard/index.html',
        stats=stats,
        recent_reservations=recent_reservations,
        tables_overview=tables_overview,
        chart_data=chart_data
    )
