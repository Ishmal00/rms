from datetime import date
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.staff import Department, Employee, Shift, Attendance, Payroll
from app.services.employee_service import EmployeeService
from app.services.staff_service import StaffService, StaffServiceError
from app.services.audit_service import AuditService
from app.utils.access_control import permission_required

staff_bp = Blueprint('staff', __name__, url_prefix='/staff')


@staff_bp.route('/')
@login_required
@permission_required('staff.manage')
def index():
    employees = Employee.query.order_by(Employee.employee_code).all()
    departments = Department.query.order_by(Department.name).all()
    shifts = Shift.query.order_by(Shift.name).all()
    today = date.today()
    today_attendances = Attendance.query.filter_by(date=today).all()

    return render_template(
        'staff/index.html',
        employees=employees,
        departments=departments,
        shifts=shifts,
        today_attendances=today_attendances,
        today=today
    )


@staff_bp.route('/employees/new', methods=['GET', 'POST'])
@login_required
@permission_required('staff.manage')
def employee_create():
    departments = Department.query.order_by(Department.name).all()
    shifts = Shift.query.order_by(Shift.name).all()
    if request.method == 'POST':
        try:
            data = request.form.to_dict()
            data['department_id'] = int(data.get('department_id', ''))
            data['shift_id'] = int(data.get('shift_id', ''))
            data['hire_date'] = date.fromisoformat(data.get('hire_date', ''))
            employee = EmployeeService.create_employee(data, user_id=current_user.id)
            flash(f'Employee {employee.full_name} created.', 'success')
            return redirect(url_for('staff.index'))
        except (ValueError, TypeError):
            flash('Enter a valid department, shift, and hire date.', 'danger')
        except StaffServiceError as exc:
            flash(str(exc), 'danger')
    return render_template(
        'staff/employee_form.html',
        employee=None,
        departments=departments,
        shifts=shifts
    )


@staff_bp.route('/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('staff.manage')
def employee_edit(employee_id):
    employee = Employee.query.filter_by(id=employee_id, is_deleted=False).first_or_404()
    departments = Department.query.order_by(Department.name).all()
    shifts = Shift.query.order_by(Shift.name).all()
    if request.method == 'POST':
        try:
            data = request.form.to_dict()
            data['department_id'] = int(data.get('department_id', ''))
            data['shift_id'] = int(data.get('shift_id', ''))
            data['hire_date'] = date.fromisoformat(data.get('hire_date', ''))
            employee = EmployeeService.update_employee(
                employee_id,
                data,
                user_id=current_user.id
            )
            flash(f'Employee {employee.full_name} updated.', 'success')
            return redirect(url_for('staff.index'))
        except (ValueError, TypeError):
            flash('Enter a valid department, shift, and hire date.', 'danger')
        except StaffServiceError as exc:
            flash(str(exc), 'danger')
    return render_template(
        'staff/employee_form.html',
        employee=employee,
        departments=departments,
        shifts=shifts
    )


@staff_bp.route('/employees/<int:employee_id>/delete', methods=['POST'])
@login_required
@permission_required('staff.manage')
def employee_delete(employee_id):
    try:
        employee = EmployeeService.delete_employee(employee_id, user_id=current_user.id)
        flash(f'Employee {employee.full_name} moved to trash.', 'success')
    except StaffServiceError as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('staff.index'))


@staff_bp.route('/attendance/clock-in', methods=['POST'])
@login_required
@permission_required('staff.manage')
def clock_in():
    employee_id = request.form.get('employee_id', type=int)
    shift_id = request.form.get('shift_id', type=int)
    notes = request.form.get('notes', '')

    try:
        att = StaffService.record_clock_in(employee_id, shift_id, notes)
        flash(f"Clocked in successfully for {att.employee.full_name} ({att.attendance_status}).", "success")
        AuditService.log('CLOCK_IN', 'Attendance', att.id, f"Employee: {att.employee.employee_code}", user_id=current_user.id)
    except StaffServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for('staff.index'))


@staff_bp.route('/attendance/clock-out/<int:attendance_id>', methods=['POST'])
@login_required
@permission_required('staff.manage')
def clock_out(attendance_id):
    notes = request.form.get('notes', '')
    try:
        att = StaffService.record_clock_out(attendance_id, notes)
        flash(f"Clocked out successfully for {att.employee.full_name}.", "success")
        AuditService.log('CLOCK_OUT', 'Attendance', att.id, f"Employee: {att.employee.employee_code}", user_id=current_user.id)
    except StaffServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for('staff.index'))


@staff_bp.route('/payroll')
@login_required
@permission_required('payroll.manage')
def payroll_list():
    payrolls = Payroll.query.order_by(Payroll.payroll_period_year.desc(), Payroll.payroll_period_month.desc()).all()
    employees = Employee.query.order_by(Employee.first_name).all()
    return render_template('staff/payroll.html', payrolls=payrolls, employees=employees)


@staff_bp.route('/payroll/generate', methods=['POST'])
@login_required
@permission_required('payroll.manage')
def generate_payroll():
    employee_id = request.form.get('employee_id', type=int)
    month = request.form.get('month', type=int)
    year = request.form.get('year', type=int)
    bonus = Decimal(request.form.get('bonus', '0.00'))
    deductions = Decimal(request.form.get('deductions', '0.00'))

    try:
        pay = StaffService.generate_payroll_slip(
            employee_id, month, year, bonus=bonus, deductions=deductions, user_id=current_user.id
        )
        flash(f"Generated payroll slip {pay.payment_reference} for {pay.employee.full_name}.", "success")
        AuditService.log('GENERATE_PAYROLL', 'Payroll', pay.id, f"Net: ${pay.net_salary}", user_id=current_user.id)
    except StaffServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for('staff.payroll_list'))


@staff_bp.route('/payroll/pay/<int:payroll_id>', methods=['POST'])
@login_required
@permission_required('payroll.manage')
def pay_payroll(payroll_id):
    ref = request.form.get('reference', '')
    try:
        pay = StaffService.mark_payroll_paid(payroll_id, reference_no=ref, user_id=current_user.id)
        flash(f"Payroll {pay.payment_reference} marked as paid.", "success")
        AuditService.log('PAY_PAYROLL', 'Payroll', pay.id, f"Paid: ${pay.net_salary}", user_id=current_user.id)
    except StaffServiceError as e:
        flash(str(e), "danger")

    return redirect(url_for('staff.payroll_list'))


@staff_bp.route('/api/data')
@login_required
@permission_required('staff.manage')
def staff_api():
    """Server-side DataTables JSON feed for staff roster."""
    from app.utils.pagination import paginate_query
    from flask import jsonify

    dept_id = request.args.get('department_id', type=int)
    query = Employee.query.filter_by(is_deleted=False)
    if dept_id:
        query = query.filter(Employee.department_id == dept_id)

    def serialize_employee(emp):
        return {
            'id': emp.id,
            'code': emp.employee_code,
            'name': emp.full_name,
            'designation': emp.designation,
            'department': emp.department.name if emp.department else '-',
            'salary': f"${float(emp.base_salary):.2f}",
            'contact': emp.emergency_contact or '-',
            'hire_date': emp.hire_date.strftime('%b %d, %Y') if emp.hire_date else '-'
        }

    res = paginate_query(
        base_query=query,
        model=Employee,
        search_fields=['employee_code', 'first_name', 'last_name', 'designation'],
        default_sort=Employee.employee_code.asc(),
        serializer_func=serialize_employee
    )
    return jsonify(res)
