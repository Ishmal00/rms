from datetime import datetime
from decimal import Decimal
from app.extensions import db
from app.models.delivery import Delivery, DeliveryAgent, DeliveryTracking
from app.models.orders import Order


class DeliveryServiceError(Exception):
    """Custom exception for delivery dispatch operations."""
    pass


class DeliveryService:
    VALID_STATUSES = ['pending', 'assigned', 'picked_up', 'in_transit', 'delivered', 'failed']

    @staticmethod
    def create_delivery_for_order(order_id, address_id, delivery_fee=Decimal('0.00'), notes=None, user_id=None):
        """Creates delivery record for a delivery order."""
        order = Order.query.get(order_id)
        if not order:
            raise DeliveryServiceError(f"Order ID {order_id} not found.")

        existing = Delivery.query.filter_by(order_id=order_id).first()
        if existing:
            return existing

        try:
            delivery = Delivery(
                order_id=order_id,
                address_id=address_id,
                delivery_fee=Decimal(str(delivery_fee)),
                delivery_status='pending',
                delivery_notes=notes,
                created_by=user_id
            )
            db.session.add(delivery)
            db.session.commit()
            return delivery
        except Exception as e:
            db.session.rollback()
            raise DeliveryServiceError(f"Failed to create delivery: {str(e)}")

    @staticmethod
    def assign_agent(delivery_id, agent_id, user_id=None):
        """
        Assigns an available delivery agent to a delivery.
        Updates agent availability and logs tracking checkpoint.
        """
        delivery = Delivery.query.get(delivery_id)
        if not delivery:
            raise DeliveryServiceError(f"Delivery ID {delivery_id} not found.")

        agent = DeliveryAgent.query.get(agent_id)
        if not agent:
            raise DeliveryServiceError(f"Delivery agent ID {agent_id} not found.")

        if not agent.is_available:
            raise DeliveryServiceError(f"Agent {agent.name} is currently unavailable.")

        try:
            # ATOMIC TRANSACTION: Assign agent, update delivery and agent status
            delivery.delivery_agent_id = agent.id
            delivery.delivery_status = 'assigned'
            delivery.assigned_at = datetime.utcnow()
            delivery.updated_by = user_id

            agent.is_available = False
            agent.updated_by = user_id

            # Create initial tracking checkpoint
            tracking = DeliveryTracking(
                delivery_id=delivery.id,
                status='assigned',
                checkpoint_notes=f"Assigned to driver {agent.name} ({agent.vehicle_type})",
                created_by=user_id
            )
            db.session.add(tracking)
            db.session.commit()
            return delivery
        except Exception as e:
            db.session.rollback()
            raise DeliveryServiceError(f"Failed to assign agent: {str(e)}")

    @staticmethod
    def advance_delivery_status(delivery_id, new_status, latitude=None, longitude=None, notes=None, user_id=None):
        """
        Advances delivery lifecycle status with tracking event logging.
        When status reaches 'delivered' or 'failed', marks delivery agent available again.
        """
        if new_status not in DeliveryService.VALID_STATUSES:
            raise DeliveryServiceError(f"Invalid delivery status: {new_status}")

        delivery = Delivery.query.get(delivery_id)
        if not delivery:
            raise DeliveryServiceError(f"Delivery ID {delivery_id} not found.")

        try:
            now = datetime.utcnow()
            delivery.delivery_status = new_status
            delivery.updated_by = user_id

            if new_status == 'picked_up':
                delivery.picked_up_at = now
            elif new_status in ['delivered', 'failed']:
                delivery.delivered_at = now
                if delivery.delivery_agent:
                    delivery.delivery_agent.is_available = True
                    delivery.delivery_agent.updated_by = user_id

            tracking = DeliveryTracking(
                delivery_id=delivery.id,
                status=new_status,
                latitude=latitude,
                longitude=longitude,
                checkpoint_notes=notes or f"Status changed to {new_status}",
                recorded_at=now,
                created_by=user_id
            )
            db.session.add(tracking)
            db.session.commit()
            return delivery
        except Exception as e:
            db.session.rollback()
            raise DeliveryServiceError(f"Failed to advance delivery status: {str(e)}")
