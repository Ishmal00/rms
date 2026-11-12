from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models.settings import SystemSetting, AuditLog
from app.services.audit_service import AuditService
from app.services.cache_service import cache
from app.utils.access_control import permission_required

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/')
@login_required
@permission_required('settings.manage')
def index():
    settings = SystemSetting.query.order_by(SystemSetting.setting_key).all()
    audit_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(50).all()

    return render_template(
        'settings/index.html',
        settings=settings,
        audit_logs=audit_logs
    )


@settings_bp.route('/update/<int:setting_id>', methods=['POST'])
@login_required
@permission_required('settings.manage')
def update_setting(setting_id):
    setting = SystemSetting.query.get_or_404(setting_id)
    new_value = request.form.get('setting_value', '').strip()

    old_val = setting.setting_value
    setting.setting_value = new_value
    setting.updated_by = current_user.id
    db.session.commit()

    flash(f"Setting '{setting.setting_key}' updated successfully.", "success")
    AuditService.log('UPDATE_SETTING', 'SystemSetting', setting.id, f"Old: {old_val} -> New: {new_value}", user_id=current_user.id)
    cache.delete_pattern('dashboard:*')
    cache.delete_pattern('reports:*')
    cache.delete_pattern('settings:*')

    return redirect(url_for('settings.index'))
