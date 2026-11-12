from decimal import Decimal
from sqlalchemy import func
from app.extensions import db
from app.models.feedback import CustomerFeedback


class FeedbackServiceError(Exception):
    """Custom exception for feedback processing."""
    pass


class FeedbackService:
    @staticmethod
    def submit_feedback(food_rating, service_rating, ambience_rating, customer_id=None, order_id=None, comments=None, user_id=None):
        """
        Creates customer feedback with calculated overall weighted rating.
        Ratings must be between 1 and 5.
        """
        for r_name, r_val in [('food_rating', food_rating), ('service_rating', service_rating), ('ambience_rating', ambience_rating)]:
            if not (1 <= int(r_val) <= 5):
                raise FeedbackServiceError(f"{r_name} must be between 1 and 5.")

        overall = ((Decimal(str(food_rating)) + Decimal(str(service_rating)) + Decimal(str(ambience_rating))) / Decimal('3.00')).quantize(Decimal('0.01'))

        try:
            feedback = CustomerFeedback(
                customer_id=customer_id,
                order_id=order_id,
                food_rating=int(food_rating),
                service_rating=int(service_rating),
                ambience_rating=int(ambience_rating),
                overall_rating=overall,
                comments=comments.strip() if comments else None,
                is_published=True,
                created_by=user_id
            )
            db.session.add(feedback)
            db.session.commit()
            return feedback
        except Exception as e:
            db.session.rollback()
            raise FeedbackServiceError(f"Failed to submit feedback: {str(e)}")

    @staticmethod
    def respond_to_feedback(feedback_id, response_notes, user_id=None):
        """Adds manager response notes to customer feedback."""
        feedback = CustomerFeedback.query.get(feedback_id)
        if not feedback:
            raise FeedbackServiceError(f"Feedback ID {feedback_id} not found.")

        feedback.response_notes = response_notes.strip()
        feedback.updated_by = user_id
        db.session.commit()
        return feedback

    @staticmethod
    def get_feedback_statistics():
        """Aggregates overall rating metrics."""
        count = CustomerFeedback.query.count()
        if count == 0:
            return {
                'total_reviews': 0,
                'avg_overall': Decimal('0.00'),
                'avg_food': Decimal('0.00'),
                'avg_service': Decimal('0.00'),
                'avg_ambience': Decimal('0.00'),
            }

        avg_overall = db.session.query(func.avg(CustomerFeedback.overall_rating)).scalar() or 0
        avg_food = db.session.query(func.avg(CustomerFeedback.food_rating)).scalar() or 0
        avg_service = db.session.query(func.avg(CustomerFeedback.service_rating)).scalar() or 0
        avg_ambience = db.session.query(func.avg(CustomerFeedback.ambience_rating)).scalar() or 0

        return {
            'total_reviews': count,
            'avg_overall': Decimal(str(avg_overall)).quantize(Decimal('0.01')),
            'avg_food': Decimal(str(avg_food)).quantize(Decimal('0.01')),
            'avg_service': Decimal(str(avg_service)).quantize(Decimal('0.01')),
            'avg_ambience': Decimal(str(avg_ambience)).quantize(Decimal('0.01')),
        }
