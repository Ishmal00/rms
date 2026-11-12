import json
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.customers import Customer
from app.models.settings import AuditLog


class CustomerServiceError(Exception):
    """Raised when customer management operations fail."""


class CustomerService:
    @staticmethod
    def create_customer(data, user_id=None):
        name = (data.get('name') or '').strip()
        phone = (data.get('phone') or '').strip()
        email = (data.get('email') or '').strip() or None
        if not name or not phone:
            raise CustomerServiceError('Customer name and phone are required.')
        if email and Customer.query.filter_by(email=email).first():
            raise CustomerServiceError('A customer with this email already exists.')

        try:
            customer = Customer(
                name=name,
                phone=phone,
                email=email,
                notes=(data.get('notes') or '').strip() or None,
                created_by=user_id
            )
            db.session.add(customer)
            db.session.flush()
            db.session.add(AuditLog(
                user_id=user_id,
                action='CREATE',
                target_entity='Customer',
                target_id=customer.id,
                details_json=json.dumps({'name': customer.name, 'phone': customer.phone}),
                created_by=user_id
            ))
            db.session.commit()
            return customer
        except IntegrityError as exc:
            db.session.rollback()
            raise CustomerServiceError('A customer with these details already exists.') from exc
        except Exception as exc:
            db.session.rollback()
            raise CustomerServiceError(f'Failed to create customer: {exc}') from exc

    @staticmethod
    def update_customer(customer_id, data, user_id=None):
        customer = Customer.query.filter_by(id=customer_id, is_deleted=False).first()
        if not customer:
            raise CustomerServiceError(f'Customer #{customer_id} was not found.')

        name = (data.get('name') or '').strip()
        phone = (data.get('phone') or '').strip()
        email = (data.get('email') or '').strip() or None
        if not name or not phone:
            raise CustomerServiceError('Customer name and phone are required.')
        if email and Customer.query.filter(
            Customer.email == email,
            Customer.id != customer.id
        ).first():
            raise CustomerServiceError('A customer with this email already exists.')

        try:
            customer.name = name
            customer.phone = phone
            customer.email = email
            customer.notes = (data.get('notes') or '').strip() or None
            customer.updated_by = user_id
            db.session.add(AuditLog(
                user_id=user_id,
                action='UPDATE',
                target_entity='Customer',
                target_id=customer.id,
                details_json=json.dumps({'name': customer.name, 'phone': customer.phone}),
                created_by=user_id
            ))
            db.session.commit()
            return customer
        except IntegrityError as exc:
            db.session.rollback()
            raise CustomerServiceError('A customer with these details already exists.') from exc
        except Exception as exc:
            db.session.rollback()
            raise CustomerServiceError(f'Failed to update customer: {exc}') from exc

    @staticmethod
    def delete_customer(customer_id, user_id=None):
        customer = Customer.query.filter_by(id=customer_id, is_deleted=False).first()
        if not customer:
            raise CustomerServiceError(f'Customer #{customer_id} was not found.')

        try:
            customer.soft_delete(user_id=user_id)
            db.session.add(AuditLog(
                user_id=user_id,
                action='DELETE',
                target_entity='Customer',
                target_id=customer.id,
                details_json=json.dumps({'name': customer.name}),
                created_by=user_id
            ))
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            raise CustomerServiceError(f'Failed to delete customer: {exc}') from exc
