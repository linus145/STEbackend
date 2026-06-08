from django.db import models
from django.conf import settings
import uuid

class UserCredit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credit",
    )
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    last_allocated_plan_type = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Credit"
        verbose_name_plural = "User Credits"

    def __str__(self):
        return f"{self.user.email} - Balance: {self.balance}"


class CreditTransaction(models.Model):
    ACTIVITY_CHOICES = (
        ("allocation", "Plan Allocation"),
        ("burn", "Credit Burn"),
        ("purchase", "Credit Purchase"),
        ("refund", "Credit Refund"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credit_transactions",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Negative for consumption, positive for replenishment/allocation.")
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_CHOICES)
    description = models.TextField(blank=True, null=True)
    module = models.CharField(max_length=100, blank=True, null=True)
    candidate_id = models.CharField(max_length=255, blank=True, null=True)
    interview_id = models.CharField(max_length=255, blank=True, null=True)
    job_id = models.CharField(max_length=255, blank=True, null=True)
    action_type = models.CharField(max_length=100, blank=True, null=True)
    metadata = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Credit Transaction"
        verbose_name_plural = "Credit Transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.activity_type} - {self.amount} - {self.created_at}"
