from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.services.report_service import ReportService
from app.utils.access_control import permission_required

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


@reports_bp.route('/')
@login_required
@permission_required('reports.view')
def index():
    force_refresh = request.args.get('refresh', '0') == '1'
    kpis = ReportService.get_financial_kpis(force_refresh=force_refresh)
    top_items = ReportService.get_top_selling_items(limit=6)
    order_types_summary = ReportService.get_order_breakdown_by_type()

    return render_template(
        'reports/index.html',
        kpis=kpis,
        top_items=top_items,
        order_types_summary=order_types_summary
    )
