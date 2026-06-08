from django.core.exceptions import PermissionDenied
from django.db import transaction
from .models import UserCredit, CreditTransaction
from subscription.models import UserSubscription

def check_and_get_user_credit(user):
    """
    Get the UserCredit object for the user. If it doesn't exist,
    initialize it based on their subscription status as a fallback.
    """
    if not user or user.is_anonymous:
        raise PermissionDenied("Authentication required to use AI features.")

    # Self-heal / initialize user credit if missing
    user_credit = UserCredit.objects.filter(user=user).first()
    if not user_credit:
        # Check active subscription
        subscription = UserSubscription.objects.filter(user=user, status="active").first()
        plan_type = "free"
        if subscription and subscription.plan:
            plan_type = subscription.plan.plan_type
        
        plan_credits = {
            "free": 100,
            "basic": 500,
            "growth": 1000,
            "enterprise": 1500
        }.get(plan_type, 100)

        user_credit = UserCredit.objects.create(
            user=user,
            balance=plan_credits,
            last_allocated_plan_type=plan_type
        )
        
        CreditTransaction.objects.create(
            user=user,
            amount=plan_credits,
            activity_type="allocation",
            description=f"Auto-initialized {plan_credits} credits for {plan_type} plan."
        )

    return user_credit

def check_credits(user, required_amount):
    """
    Check if a user has at least the required amount of credits.
    """
    try:
        from decimal import Decimal
        user_credit = check_and_get_user_credit(user)
        return user_credit.balance >= Decimal(str(required_amount))
    except Exception:
        return False

def burn_credits(user, amount, description="AI usage", module=None, candidate_id=None, interview_id=None, job_id=None, action_type=None, metadata=None):
    """
    Deduct the specified amount of credits from the user's balance.
    Raises PermissionDenied if the balance is insufficient.
    """
    from decimal import Decimal
    amount_dec = Decimal(str(amount))
    with transaction.atomic():
        user_credit = check_and_get_user_credit(user)
        
        if user_credit.balance < amount_dec:
            raise PermissionDenied(
                f"Insufficient credits. This task requires {amount} credits, but you only have {user_credit.balance} remaining."
            )
            
        user_credit.balance -= amount_dec
        user_credit.save()
        
        CreditTransaction.objects.create(
            user=user,
            amount=-amount_dec,
            activity_type="burn",
            description=description,
            module=module,
            candidate_id=candidate_id,
            interview_id=interview_id,
            job_id=job_id,
            action_type=action_type,
            metadata=metadata
        )
        
    return user_credit.balance
