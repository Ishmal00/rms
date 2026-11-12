import uuid
from datetime import datetime, date
from decimal import Decimal
from app.extensions import db
from app.models.staff import Employee, Shift, Attendance, Payroll


class StaffServiceError(Exception):
    """Custom exception for staff management errors."""
    pass


class StaffService:
    @staticmethod
    def record_clock_in(employee_id, shift_id=None, notes=None):
        """
        Records a staff clock-in. Prevents double clock-in for the same day without clocking out.
        """
        employee = Employee.query.get(employee_id)
        if not employee:
            raise StaffServiceError(f"Employee ID {employee_id} not found.")

        today = date.today()
        # Check if already clocked in today without clocking out
        active_attendance = Attendance.query.filter(
            Attendance.employee_id == employee_id,
            Attendance.date == today,
            Attendance.clock_out.is_(None)
        ).first()

        if active_attendance:
            raise StaffServiceError(f"Employee {employee.full_name} is already clocked in today at {active_attendance.clock_in}.")

        now = datetime.utcnow()
        status = 'present'
        if shift_id:
            shift = Shift.query.get(shift_id)
            if shift and now.time() > shift.start_time:
                status = 'late'

        attendance = Attendance(
            employee_id=employee_id,
            shift_id=shift_id,
            date=today,
            clock_in=now,
            attendance_status=status,
            notes=notes
        )
        db.session.add(attendance)
        db.session.commit()
        return attendance

    @staticmethod
    def record_clock_out(attendance_id, notes=None):
        """Records staff clock-out and updates attendance note."""
        attendance = Attendance.query.get(attendance_id)
        if not attendance:
            raise StaffServiceError(f"Attendance ID {attendance_id} not found.")

        if attendance.clock_out is not None:
            raise StaffServiceError("Attendance record already clocked out.")

        attendance.clock_out = datetime.utcnow()
        if notes:
            attendance.notes = (attendance.notes or '') + f" [Out: {notes}]"

        db.session.commit()
        return attendance

    @staticmethod
    def generate_payroll_slip(employee_id, month, year, bonus=Decimal('0.00'), deductions=Decimal('0.00'), user_id=None):
        """
        Generates monthly payroll slip within an atomic transaction.
        Formula: net_salary = base_salary + bonus - deductions.
        """
        employee = Employee.query.get(employee_id)
        if not employee:
            raise StaffServiceError(f"Employee ID {employee_id} not found.")

        # Check if payroll already generated for this month/year
        existing = Payroll.query.filter_by(
            employee_id=employee_id,
            payroll_period_month=month,
            payroll_period_year=year
        ).first()
        if existing:
            raise StaffServiceError(f"Payroll for {year}-{month:02d} already generated for employee {employee.full_name}.")

        base = Decimal(str(employee.base_salary))
        bonus = Decimal(str(bonus))
        deductions = Decimal(str(deductions))
        net = (base + bonus) - deductions
        if net < Decimal('0.00'):
            net = Decimal('0.00')

        try:
            # ATOMIC TRANSACTION: Generate payroll slip
            ref = f"PAYROLL-{year}{month:02d}-{employee.employee_code}-{uuid.uuid4().hex[:4].upper()}"
            payroll = Payroll(
                employee_id=employee_id,
                payroll_period_month=month,
                payroll_period_year=year,
                base_salary=base,
                bonus=bonus,
                deductions=deductions,
                net_salary=net,
                payment_status='unpaid',
                payment_reference=ref,
                created_by=user_id
            )
            db.session.add(payroll)
            db.session.commit()
            return payroll
        except Exception as e:
            db.session.rollback()
            raise StaffServiceError(f"Failed to generate payroll: {str(e)}")

    @staticmethod
    def mark_payroll_paid(payroll_id, reference_no=None, user_id=None):
        """Marks a payroll slip as paid."""
        payroll = Payroll.query.get(payroll_id)
        if not payroll:
            raise StaffServiceError(f"Payroll record {payroll_id} not found.")

        if payroll.payment_status == 'paid':
            raise StaffServiceError("Payroll has already been paid.")

        try:
            payroll.payment_status = 'paid'
            payroll.payment_date = datetime.utcnow()
            if reference_no:
                payroll.payment_reference = reference_no
            payroll.updated_by = user_id
            db.session.commit()
            return payroll
        except Exception as e:
            db.session.rollback()
            raise StaffServiceError(f"Failed to update payroll status: {str(e)}")
