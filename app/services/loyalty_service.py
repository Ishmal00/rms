from decimal import Decimal
from app.extensions import db
from app.models.customers import Customer
from app.models.loyalty import LoyaltyProgram, LoyaltyTransaction, Reward


class LoyaltyServiceError(Exception):
    """Custom exception for loyalty operations."""
    pass


class LoyaltyService:
    @staticmethod
    def get_customer_tier(customer):
        """Returns the customer's current loyalty tier based on accrued points/spend."""
        points = customer.loyalty_points or 0
        tiers = LoyaltyProgram.query.filter_by(status='active').order_by(LoyaltyProgram.min_spend.desc()).all()
        for tier in tiers:
            # 10 points per dollar equivalent
            if Decimal(str(points)) >= (tier.min_spend * Decimal('10')):
                return tier
        return tiers[-1] if tiers else None

    @staticmethod
    def award_points_for_order(customer_id, order_id, total_amount, user_id=None):
        """
        Awards loyalty points based on order total.
        Formula: points = floor(total_amount * points_per_dollar).
        Updates customer loyalty_points and writes LoyaltyTransaction ledger.
        """
        customer = Customer.query.get(customer_id)
        if not customer:
            return None

        tier = LoyaltyService.get_customer_tier(customer)
        multiplier = tier.points_per_dollar if tier else Decimal('1.00')

        earned_points = int(Decimal(str(total_amount)) * multiplier)
        if earned_points <= 0:
            return None

        try:
            # ATOMIC TRANSACTION: Award loyalty points
            customer.loyalty_points = (customer.loyalty_points or 0) + earned_points
            customer.updated_by = user_id

            tx = LoyaltyTransaction(
                customer_id=customer.id,
                order_id=order_id,
                points=earned_points,
                transaction_type='earn',
                balance_after=customer.loyalty_points,
                notes=f"Earned from order #{order_id} ({multiplier} pts/$)",
                created_by=user_id
            )
            db.session.add(tx)
            db.session.commit()
            return tx
        except Exception as e:
            db.session.rollback()
            raise LoyaltyServiceError(f"Failed to award loyalty points: {str(e)}")

    award_order_points = award_points_for_order

    @staticmethod
    def redeem_points(customer_id, points_to_burn, order_id=None, user_id=None):
        """
        Burns loyalty points in exchange for billing credit.
        Returns monetary discount value.
        """
        customer = Customer.query.get(customer_id)
        if not customer:
            raise LoyaltyServiceError(f"Customer ID {customer_id} not found.")

        points_to_burn = int(points_to_burn)
        if points_to_burn <= 0:
            raise LoyaltyServiceError("Points to redeem must be greater than zero.")

        current_balance = customer.loyalty_points or 0
        if current_balance < points_to_burn:
            raise LoyaltyServiceError(f"Insufficient points. Balance is {current_balance}, requested {points_to_burn}.")

        tier = LoyaltyService.get_customer_tier(customer)
        discount_rate = tier.discount_per_point if tier else Decimal('0.0100')
        monetary_discount = (Decimal(str(points_to_burn)) * discount_rate).quantize(Decimal('0.01'))

        try:
            # ATOMIC TRANSACTION: Burn points
            customer.loyalty_points = current_balance - points_to_burn
            customer.updated_by = user_id

            tx = LoyaltyTransaction(
                customer_id=customer.id,
                order_id=order_id,
                points=-points_to_burn,
                transaction_type='redeem',
                balance_after=customer.loyalty_points,
                notes=f"Redeemed {points_to_burn} points for ${monetary_discount} discount",
                created_by=user_id
            )
            db.session.add(tx)
            db.session.commit()
            return monetary_discount, tx
        except Exception as e:
            db.session.rollback()
            raise LoyaltyServiceError(f"Failed to redeem points: {str(e)}")

    @staticmethod
    def redeem_reward(customer_id, reward_id, user_id=None):
        """Redeems a catalog reward using loyalty points."""
        customer = Customer.query.get(customer_id)
        if not customer:
            raise LoyaltyServiceError(f"Customer ID {customer_id} not found.")

        reward = Reward.query.get(reward_id)
        if not reward or not reward.is_active:
            raise LoyaltyServiceError(f"Reward ID {reward_id} is invalid or inactive.")

        current_balance = customer.loyalty_points or 0
        if current_balance < reward.points_required:
            raise LoyaltyServiceError(f"Need {reward.points_required} points for '{reward.title}', current balance is {current_balance}.")

        try:
            customer.loyalty_points = current_balance - reward.points_required
            customer.updated_by = user_id

            tx = LoyaltyTransaction(
                customer_id=customer.id,
                points=-reward.points_required,
                transaction_type='redeem',
                balance_after=customer.loyalty_points,
                notes=f"Redeemed reward: {reward.title}",
                created_by=user_id
            )
            db.session.add(tx)
            db.session.commit()
            return reward, tx
        except Exception as e:
            db.session.rollback()
            raise LoyaltyServiceError(f"Failed to redeem reward: {str(e)}")
