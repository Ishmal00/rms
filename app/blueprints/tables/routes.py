from flask import Blueprint, render_template, request
from flask_login import login_required
from app.models.tables import RestaurantTable, Reservation

tables_bp = Blueprint('tables', __name__, url_prefix='/tables')


@tables_bp.route('/')
@login_required
def index():
    zone = request.args.get('zone', '', type=str)
    status = request.args.get('status', '', type=str)

    query = RestaurantTable.query

    if zone:
        query = query.filter(RestaurantTable.location_zone == zone)
    if status:
        query = query.filter(RestaurantTable.table_status == status)

    tables = query.order_by(RestaurantTable.table_number.asc()).all()

    reservations = Reservation.query.order_by(
        Reservation.reservation_time.asc()
    ).limit(10).all()

    # Get distinct zones
    zones = [z[0] for z in RestaurantTable.query.with_entities(RestaurantTable.location_zone).distinct().all()]

    return render_template(
        'tables/index.html',
        tables=tables,
        reservations=reservations,
        zones=zones,
        selected_zone=zone,
        selected_status=status
    )
