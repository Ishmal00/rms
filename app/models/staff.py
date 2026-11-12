from app.extensions import db
from app.models.base import BaseModel


class Department(BaseModel):
    """Organizational departments (Kitchen, Front of House, Delivery, etc.)."""
    __tablename__ = 'departments'

    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=True)

    employees = db.relationship('Employee', back_populates='department', lazy='dynamic')

    def __repr__(self):
        return f"<Department {self.name}>"


class Employee(BaseModel):
    """Staff profiles linked to user accounts and departments."""
    __tablename__ = 'employees'

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', name='fk_employees_user_id', ondelete='SET NULL'),
        nullable=True,
        unique=True
    )
    department_id = db.Column(
        db.Integer,
        db.ForeignKey('departments.id', name='fk_employees_department_id', ondelete='RESTRICT'),
        nullable=False,
        index=True
    )
    shift_id = db.Column(
        db.Integer,
        db.ForeignKey('shifts.id', name='fk_employees_shift_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    employee_code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    designation = db.Column(db.String(100), nullable=False)
    hire_date = db.Column(db.Date, nullable=False)
    base_salary = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    emergency_contact = db.Column(db.String(100), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('employee_profile', uselist=False))
    department = db.relationship('Department', back_populates='employees')
    shift = db.relationship('Shift', back_populates='employees', foreign_keys=[shift_id])
    attendances = db.relationship('Attendance', back_populates='employee', lazy='dynamic', cascade='all, delete-orphan')
    payrolls = db.relationship('Payroll', back_populates='employee', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __repr__(self):
        return f"<Employee {self.employee_code} - {self.full_name}>"


class Shift(BaseModel):
    """Work shift templates (Morning, Evening, Night)."""
    __tablename__ = 'shifts'

    name = db.Column(db.String(100), nullable=False, unique=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    description = db.Column(db.String(255), nullable=True)

    attendances = db.relationship('Attendance', back_populates='shift', lazy='dynamic')
    employees = db.relationship('Employee', back_populates='shift', foreign_keys='Employee.shift_id', lazy='dynamic')

    def __repr__(self):
        return f"<Shift {self.name} ({self.start_time}-{self.end_time})>"


class Attendance(BaseModel):
    """Daily staff attendance and clock-in/out records."""
    __tablename__ = 'attendances'

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey('employees.id', name='fk_attendances_employee_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    shift_id = db.Column(
        db.Integer,
        db.ForeignKey('shifts.id', name='fk_attendances_shift_id', ondelete='SET NULL'),
        nullable=True
    )
    date = db.Column(db.Date, nullable=False, index=True)
    clock_in = db.Column(db.DateTime, nullable=False)
    clock_out = db.Column(db.DateTime, nullable=True)
    attendance_status = db.Column(db.String(20), default='present', nullable=False)  # present, late, absent, half_day
    notes = db.Column(db.Text, nullable=True)

    employee = db.relationship('Employee', back_populates='attendances')
    shift = db.relationship('Shift', back_populates='attendances')

    def __repr__(self):
        return f"<Attendance emp={self.employee_id} date={self.date} status={self.attendance_status}>"


class Payroll(BaseModel):
    """Monthly salary and payroll slips."""
    __tablename__ = 'payrolls'

    employee_id = db.Column(
        db.Integer,
        db.ForeignKey('employees.id', name='fk_payrolls_employee_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    payroll_period_month = db.Column(db.Integer, nullable=False)
    payroll_period_year = db.Column(db.Integer, nullable=False)
    base_salary = db.Column(db.Numeric(10, 2), nullable=False)
    bonus = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    deductions = db.Column(db.Numeric(10, 2), default=0.00, nullable=False)
    net_salary = db.Column(db.Numeric(10, 2), nullable=False)
    payment_status = db.Column(db.String(20), default='unpaid', nullable=False)  # unpaid, paid
    payment_date = db.Column(db.DateTime, nullable=True)
    payment_reference = db.Column(db.String(100), unique=True, nullable=True)

    employee = db.relationship('Employee', back_populates='payrolls')

    def __repr__(self):
        return f"<Payroll emp={self.employee_id} {self.payroll_period_year}-{self.payroll_period_month} net={self.net_salary}>"
