from django.db import models
from django.conf import settings
import uuid


class SubscriptionPlan(models.Model):
    PLAN_TYPE_CHOICES = (
        ("free", "Free"),
        ("basic", "Basic"),
        ("growth", "Growth"),
        ("enterprise", "Enterprise"),
    )

    BILLING_TYPE_CHOICES = (
        ("monthly", "Monthly"),
        ("yearly", "Yearly"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        max_length=150,
    )

    slug = models.SlugField(
        unique=True,
        null=True,
        blank=True,
    )

    plan_type = models.CharField(
        max_length=20,
        choices=PLAN_TYPE_CHOICES,
        default="free",
    )

    billing_type = models.CharField(
        max_length=20,
        choices=BILLING_TYPE_CHOICES,
        default="monthly",
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    employee_limit = models.CharField(
        max_length=100,
        help_text="Example: 1-10 Employees",
    )

    short_tagline = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Example: Complete AI Hiring Suite",
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    badge_text = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Example: Most Popular",
    )

    is_popular = models.BooleanField(
        default=False,
    )

    is_active = models.BooleanField(
        default=True,
    )

    display_order = models.PositiveIntegerField(
        default=0,
    )

    # =========================================================
    # CORE MODULE ACCESS
    # =========================================================

    has_user_dashboard = models.BooleanField(default=False)

    has_ai_interview_pipeline = models.BooleanField(default=False)

    has_hr_toolkit = models.BooleanField(default=False)

    has_ai_resume_screening = models.BooleanField(default=False)

    has_candidate_evaluation = models.BooleanField(default=False)

    has_hiring_workflow_automation = models.BooleanField(default=False)

    has_interview_scheduling = models.BooleanField(default=False)

    has_offer_letter_management = models.BooleanField(default=False)

    has_employee_onboarding = models.BooleanField(default=False)

    has_task_management = models.BooleanField(default=False)

    has_team_collaboration = models.BooleanField(default=False)

    has_email_automation = models.BooleanField(default=False)

    has_analytics_dashboard = models.BooleanField(default=False)

    has_custom_workflows = models.BooleanField(default=False)

    has_api_access = models.BooleanField(default=False)

    has_third_party_integrations = models.BooleanField(default=False)

    has_role_based_access = models.BooleanField(default=False)

    has_ai_hiring_agent = models.BooleanField(default=False)

    has_autonomous_ai_agents = models.BooleanField(default=False)

    has_predictive_ai_analytics = models.BooleanField(default=False)

    has_priority_support = models.BooleanField(default=False)

    has_dedicated_manager = models.BooleanField(default=False)

    # =========================================================
    # FEATURE GROUP TEXTS
    # =========================================================

    agent_intelligence_type = models.TextField(
        blank=True,
        null=True,
    )

    hiring_ats_automation = models.TextField(
        blank=True,
        null=True,
    )

    onboarding_workflow = models.TextField(
        blank=True,
        null=True,
    )

    employee_self_service = models.TextField(
        blank=True,
        null=True,
    )

    system_integrations = models.TextField(
        blank=True,
        null=True,
    )

    analytics_governance = models.TextField(
        blank=True,
        null=True,
    )

    # =========================================================
    # UI DISPLAY FEATURES
    # =========================================================

    highlights = models.JSONField(
        default=list,
        blank=True,
        help_text="List of feature highlights",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "Subscription Plan"
        verbose_name_plural = "Subscription Plans"
        ordering = ["display_order", "price"]

    def __str__(self):
        return f"{self.name} - ₹{self.price}"


class UserSubscription(models.Model):
    STATUS_CHOICES = (
        ("active", "Active"),
        ("pending", "Pending"),
        ("expired", "Expired"),
        ("canceled", "Canceled"),
        ("trial", "Trial"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription",
    )

    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    start_date = models.DateTimeField(
        auto_now_add=True,
    )

    end_date = models.DateTimeField(
        null=True,
        blank=True,
    )

    auto_renew = models.BooleanField(
        default=True,
    )

    payment_reference = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "User Subscription"
        verbose_name_plural = "User Subscriptions"

    def __str__(self):
        plan_name = self.plan.name if self.plan else "No Plan"

        return (
            f"{self.user.email} - "
            f"{plan_name} ({self.status})"
        )


class ManualPayment(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending Verification"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    PAYMENT_TYPE_CHOICES = (
        ("new", "New Subscription"),
        ("upgrade", "Upgrading Subscription"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="manual_payments",
    )
    subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.CASCADE,
        related_name="manual_payments",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.CASCADE,
        related_name="manual_payments",
    )
    transaction_id = models.CharField(
        max_length=255,
        unique=True,
    )
    payment_method = models.CharField(
        max_length=100,
        help_text="e.g. UPI, GPay, PhonePe, Net Banking",
    )
    payment_type = models.CharField(
        max_length=20,
        choices=PAYMENT_TYPE_CHOICES,
        default="new",
        help_text="Whether this is a new subscription or an upgrade",
    )
    upgrade_upi_or_phone = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="PhonePe Number or UPI ID (required only when payment_type is 'upgrade')",
    )
    screenshot = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="ImageKit CDN URL for transaction screenshot",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Reason for rejection or admin notes",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "Manual Payment Verification"
        verbose_name_plural = "Manual Payment Verifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.plan.name} - {self.status}"

    def save(self, *args, **kwargs):
        is_adding = self._state.adding
        old_status = None
        if not is_adding:
            try:
                old_status = ManualPayment.objects.get(pk=self.pk).status
            except ManualPayment.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # When status transitions to 'approved', automatically activate the associated subscription
        if self.status == "approved" and old_status != "approved":
            subscription = self.subscription
            subscription.plan = self.plan
            subscription.status = "active"
            subscription.save()