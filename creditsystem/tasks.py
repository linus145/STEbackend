from celery import shared_task
from django.db import transaction
from subscription.models import UserSubscription
from .models import UserCredit, CreditTransaction

@shared_task
def replenish_monthly_credits():
    """
    Celery task to replenish credits for all active subscriptions.
    Usually scheduled to run once a month.
    """
    active_subscriptions = UserSubscription.objects.filter(status="active").select_related("user", "plan")
    
    replenished_count = 0
    
    for sub in active_subscriptions:
        if not sub.plan:
            continue
            
        plan_type = sub.plan.plan_type
        plan_credits = {
            "free": 100,
            "basic": 500,
            "growth": 1000,
            "enterprise": 1500
        }.get(plan_type, 100)
        
        with transaction.atomic():
            user_credit, created = UserCredit.objects.get_or_create(
                user=sub.user,
                defaults={
                    "balance": plan_credits,
                    "last_allocated_plan_type": plan_type
                }
            )
            
            old_balance = user_credit.balance
            user_credit.balance = plan_credits
            user_credit.last_allocated_plan_type = plan_type
            user_credit.save()
            
            # Log the replenishment transaction (difference added/allocated)
            added_credits = plan_credits - old_balance
            CreditTransaction.objects.create(
                user=sub.user,
                amount=added_credits,
                activity_type="allocation",
                description=f"Monthly credit replenishment. Refilled to {plan_credits} credits (added {added_credits}) for {sub.plan.name} plan."
            )
            replenished_count += 1
            
    return f"Successfully replenished credits for {replenished_count} active users."
