from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.tables import RestaurantTable, Reservation
from app.services.status_service import StatusService, StatusServiceError
from app.utils.access_control import permission_required

tables_bp = Blueprint('tables', __name__, url_prefix='/tables')


@tables_bp.route('/')
@login_required
@permission_required('tables.manage')
def index():
    zone = request.args.get('zone', '', type=str)
    table_status = request.args.get('status', '', type=str)
    active_status = request.args.get('active_status', '', type=str)
    search = request.args.get('q', '', type=str).strip()

    query = RestaurantTable.query.filter_by(is_deleted=False)

    if zone:
        query = query.filter(RestaurantTable.location_zone == zone)
    if table_status:
        query = query.filter(RestaurantTable.table_status == table_status)
    if active_status in ('active', 'deactive'):
        query = query.filter(RestaurantTable.status == active_status)
    if search:
        query = query.filter(
            RestaurantTable.table_number.ilike(f'%{search}%')
            | RestaurantTable.location_zone.ilike(f'%{search}%')
        )

    table_pagination = query.order_by(RestaurantTable.table_number.asc()).paginate(
        page=request.args.get('table_page', 1, type=int),
        per_page=8,
        error_out=False
    )

    reservation_search = request.args.get('reservation_q', '', type=str).strip()
    reservation_status = request.args.get('reservation_status', '', type=str)
    reservation_record_status = request.args.get('reservation_record_status', '', type=str)
    reservation_query = Reservation.query.filter_by(is_deleted=False)
    if reservation_search:
        pattern = f'%{reservation_search}%'
        reservation_query = reservation_query.filter(
            Reservation.customer_name.ilike(pattern)
            | Reservation.customer_phone.ilike(pattern)
            | Reservation.customer_email.ilike(pattern)
        )
    if reservation_status:
        reservation_query = reservation_query.filter(Reservation.reservation_status == reservation_status)
    if reservation_record_status in ('active', 'deactive'):
        reservation_query = reservation_query.filter(Reservation.status == reservation_record_status)
    reservation_page = reservation_query.order_by(Reservation.reservation_time.asc()).paginate(
        page=request.args.get('reservation_page', 1, type=int),
        per_page=10,
        error_out=False
    )

    # Get distinct zones
    zones = [z[0] for z in RestaurantTable.query.filter_by(is_deleted=False).with_entities(RestaurantTable.location_zone).distinct().all()]

    return render_template(
        'tables/index.html',
        tables=table_pagination.items,
        table_pagination=table_pagination,
        reservations=reservation_page.items,
        reservation_pagination=reservation_page,
        zones=zones,
        selected_zone=zone,
        selected_status=table_status,
        active_status=active_status,
        search=search,
        reservation_search=reservation_search,
        reservation_status=reservation_status,
        reservation_record_status=reservation_record_status
    )


@tables_bp.route('/<int:table_id>/toggle-status', methods=['POST'])
@login_required
@permission_required('tables.manage')
def toggle_table_status(table_id):
    table = RestaurantTable.query.filter_by(id=table_id, is_deleted=False).first_or_404()
    try:
        StatusService.toggle(table, current_user.id)
        flash(f'Table status changed to {table.status}.', 'success')
    except StatusServiceError as exc:
        flash(str(exc), 'danger')
    return redirect(request.referrer or url_for('tables.index'))


@tables_bp.route('/reservations/<int:reservation_id>/toggle-status', methods=['POST'])
@login_required
@permission_required('tables.manage')
def toggle_reservation_status(reservation_id):
    reservation = Reservation.query.filter_by(id=reservation_id, is_deleted=False).first_or_404()
    try:
        StatusService.toggle(reservation, current_user.id)
        flash(f'Reservation status changed to {reservation.status}.', 'success')
    except StatusServiceError as exc:
        flash(str(exc), 'danger')
    return redirect(request.referrer or url_for('tables.index'))
