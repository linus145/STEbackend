from django.db.models.signals import post_save
from django.dispatch import receiver
from subscription.models import UserSubscription
from .models import UserCredit, CreditTransaction

@receiver(post_save, sender=UserSubscription)
def handle_subscription_update(sender, instance, created, **kwargs):
    # We only allocate credits if the status is active and a plan is set
    if instance.status == "active" and instance.plan:
        plan_type = instance.plan.plan_type
        plan_credits = {
            "free": 100,
            "basic": 500,
            "growth": 1000,
            "enterprise": 1500
        }.get(plan_type, 100) # Default to 100 for safety

        user_credit, credit_created = UserCredit.objects.get_or_create(
            user=instance.user,
            defaults={
                "balance": plan_credits,
                "last_allocated_plan_type": plan_type
            }
        )

        if credit_created:
            # Log the transaction
            CreditTransaction.objects.create(
                user=instance.user,
                amount=plan_credits,
                activity_type="allocation",
                description=f"Initial allocation of {plan_credits} credits for {instance.plan.name} plan."
            )
        else:
            # If they already had a record but the plan has changed, we should adjust/update their credits.
            if user_credit.last_allocated_plan_type != plan_type:
                old_plan = user_credit.last_allocated_plan_type
                user_credit.balance = plan_credits
                user_credit.last_allocated_plan_type = plan_type
                user_credit.save()

                CreditTransaction.objects.create(
                    user=instance.user,
                    amount=plan_credits,
                    activity_type="allocation",
                    description=f"Allocated {plan_credits} credits for switching plan from {old_plan} to {instance.plan.name}."
                )
