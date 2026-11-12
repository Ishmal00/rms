import csv
from datetime import date, timedelta
from io import StringIO

from flask import Blueprint, Response, flash, render_template, request
from flask_login import login_required
from app.services.report_service import ReportService
from app.utils.access_control import permission_required

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


@reports_bp.route('/')
@login_required
@permission_required('reports.view')
def index():
    force_refresh = request.args.get('refresh', '0') == '1'
    today = date.today()
    default_start = today - timedelta(days=29)
    start_date = _parse_date('start_date', default_start)
    end_date = _parse_date('end_date', today)
    if start_date is None or end_date is None or end_date < start_date:
        flash('Choose a valid date range with the start date on or before the end date.', 'warning')
        start_date, end_date = default_start, today

    kpis = ReportService.get_financial_kpis(force_refresh=force_refresh)
    top_items = ReportService.get_top_selling_items(limit=6)
    order_types_summary = ReportService.get_order_breakdown_by_type()
    sales_expenses = ReportService.get_sales_expense_report(
        start_date,
        end_date,
        force_refresh=force_refresh
    )

    return render_template(
        'reports/index.html',
        kpis=kpis,
        top_items=top_items,
        order_types_summary=order_types_summary,
        sales_expenses=sales_expenses,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat()
    )


def _parse_date(name, default):
    value = request.args.get(name)
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@reports_bp.route('/export/<report_type>.csv')
@login_required
@permission_required('reports.view')
def export_csv(report_type):
    today = date.today()
    default_start = today - timedelta(days=29)
    start_date = _parse_date('start_date', default_start)
    end_date = _parse_date('end_date', today)
    if start_date is None or end_date is None or end_date < start_date:
        flash('Choose a valid date range before exporting.', 'warning')
        return Response('Invalid date range.\n', status=400, mimetype='text/plain')

    exports = {
        'sales': (
            ['Payment Date', 'Transaction Reference', 'Invoice', 'Order', 'Payment Method', 'Amount'],
            ReportService.get_sales_export_rows
        ),
        'expenses': (
            ['Expense Date', 'Title', 'Category', 'Amount', 'Payment Method', 'Receipt Reference'],
            ReportService.get_expense_export_rows
        ),
    }
    if report_type not in exports:
        return Response('Unknown report type.\n', status=404, mimetype='text/plain')

    headers, get_rows = exports[report_type]
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(get_rows(start_date, end_date))
    filename = f'{report_type}_{start_date.isoformat()}_{end_date.isoformat()}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )
