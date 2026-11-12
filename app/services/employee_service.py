import json
from decimal import Decimal, InvalidOperation
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.staff import Department, Employee, Shift
from app.models.settings import AuditLog
from app.services.staff_service import StaffServiceError


class EmployeeService:
    @staticmethod
    def _values(data):
        first_name = (data.get('first_name') or '').strip()
        last_name = (data.get('last_name') or '').strip()
        employee_code = (data.get('employee_code') or '').strip()
        designation = (data.get('designation') or '').strip()
        department_id = data.get('department_id')
        shift_id = data.get('shift_id')
        hire_date = data.get('hire_date')
        try:
            salary = Decimal(str(data.get('base_salary', '0'))).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError):
            raise StaffServiceError('Base salary must be a valid amount.')

        if not all((first_name, last_name, employee_code, designation, department_id, shift_id, hire_date)):
            raise StaffServiceError('Employee name, code, department, designation, shift, and hire date are required.')
        if salary < 0:
            raise StaffServiceError('Base salary cannot be negative.')
        if not Department.query.filter_by(id=department_id, is_deleted=False).first():
            raise StaffServiceError('Select a valid department.')
        if not Shift.query.filter_by(id=shift_id, is_deleted=False).first():
            raise StaffServiceError('Select a valid shift.')

        return {
            'first_name': first_name,
            'last_name': last_name,
            'employee_code': employee_code,
            'designation': designation,
            'department_id': department_id,
            'shift_id': shift_id,
            'hire_date': hire_date,
            'base_salary': salary,
            'emergency_contact': (data.get('emergency_contact') or '').strip() or None
        }

    @staticmethod
    def _audit(action, employee, user_id):
        db.session.add(AuditLog(
            user_id=user_id,
            action=action,
            target_entity='Employee',
            target_id=employee.id,
            details_json=json.dumps({
                'employee_code': employee.employee_code,
                'name': employee.full_name
            }),
            created_by=user_id
        ))

    @staticmethod
    def create_employee(data, user_id=None):
        values = EmployeeService._values(data)
        if Employee.query.filter_by(employee_code=values['employee_code']).first():
            raise StaffServiceError('An employee with this code already exists.')

        try:
            employee = Employee(**values, created_by=user_id)
            db.session.add(employee)
            db.session.flush()
            EmployeeService._audit('CREATE', employee, user_id)
            db.session.commit()
            return employee
        except IntegrityError as exc:
            db.session.rollback()
            raise StaffServiceError('Employee code is already in use.') from exc
        except Exception as exc:
            db.session.rollback()
            raise StaffServiceError(f'Failed to create employee: {exc}') from exc

    @staticmethod
    def update_employee(employee_id, data, user_id=None):
        employee = Employee.query.filter_by(id=employee_id, is_deleted=False).first()
        if not employee:
            raise StaffServiceError(f'Employee #{employee_id} was not found.')
        values = EmployeeService._values(data)
        if Employee.query.filter(
            Employee.employee_code == values['employee_code'],
            Employee.id != employee.id
        ).first():
            raise StaffServiceError('An employee with this code already exists.')

        try:
            for key, value in values.items():
                setattr(employee, key, value)
            employee.updated_by = user_id
            EmployeeService._audit('UPDATE', employee, user_id)
            db.session.commit()
            return employee
        except IntegrityError as exc:
            db.session.rollback()
            raise StaffServiceError('Employee code is already in use.') from exc
        except Exception as exc:
            db.session.rollback()
            raise StaffServiceError(f'Failed to update employee: {exc}') from exc

    @staticmethod
    def delete_employee(employee_id, user_id=None):
        employee = Employee.query.filter_by(id=employee_id, is_deleted=False).first()
        if not employee:
            raise StaffServiceError(f'Employee #{employee_id} was not found.')

        try:
            employee.soft_delete(user_id=user_id)
            EmployeeService._audit('DELETE', employee, user_id)
            db.session.commit()
            return employee
        except Exception as exc:
            db.session.rollback()
            raise StaffServiceError(f'Failed to delete employee: {exc}') from exc
