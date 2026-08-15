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


class ManualCreditVerification(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending Verification"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="manual_credit_verifications",
    )
    credits_requested = models.DecimalField(max_digits=10, decimal_places=2, help_text="Number of AI credits requested")
    package_name = models.CharField(max_length=150, default="Credit Top-up")
    amount_paid = models.CharField(max_length=50, blank=True, null=True, help_text="Amount paid e.g. ₹499")
    transaction_id = models.CharField(max_length=255, help_text="UPI Ref No / Transaction Reference ID")
    payment_method = models.CharField(max_length=100, default="UPI / GPay / PhonePe")
    upi_or_phone = models.CharField(max_length=255, blank=True, null=True, help_text="Sender UPI ID or Phone number")
    screenshot = models.TextField(blank=True, null=True, help_text="URL or Base64 data of payment screenshot")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    notes = models.TextField(blank=True, null=True, help_text="Admin notes or rejection reasons")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Manual Credit Verification"
        verbose_name_plural = "Manual Credit Verifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.package_name} ({self.credits_requested} Credits) - {self.status}"

    def save(self, *args, **kwargs):
        is_adding = self._state.adding
        old_status = None
        if not is_adding:
            try:
                old_status = ManualCreditVerification.objects.get(pk=self.pk).status
            except ManualCreditVerification.DoesNotExist:
                pass

        super().save(*args, **kwargs)

        # When status transitions to 'approved', automatically credit user account & update credit transaction log
        if self.status == "approved" and old_status != "approved":
            user_credit, created = UserCredit.objects.get_or_create(user=self.user)
            old_balance = float(user_credit.balance)
            credits_to_add = float(self.credits_requested)

            user_credit.balance = float(user_credit.balance) + credits_to_add
            user_credit.save()

            # Find matching pending transaction log or create approved transaction log
            tx = CreditTransaction.objects.filter(
                user=self.user,
                metadata__transaction_id=self.transaction_id
            ).first()

            desc = (
                f"Purchased & Verified - Txn ID: {self.transaction_id} ({self.package_name}) via {self.payment_method}. "
                f"Balance increased from {old_balance:.0f} to {user_credit.balance:.0f}."
            )

            if tx:
                tx.description = desc
                if not tx.metadata:
                    tx.metadata = {}
                tx.metadata["status"] = "approved"
                tx.save()
            else:
                CreditTransaction.objects.create(
                    user=self.user,
                    activity_type="purchase",
                    amount=credits_to_add,
                    description=desc,
                    metadata={
                        "transaction_id": self.transaction_id,
                        "payment_method": self.payment_method,
                        "upi_or_phone": self.upi_or_phone,
                        "package_name": self.package_name,
                        "screenshot": self.screenshot,
                        "status": "approved"
                    }
                )

