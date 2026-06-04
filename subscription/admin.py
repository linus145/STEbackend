from django.contrib import admin
from .models import SubscriptionPlan, UserSubscription, ManualPayment

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "plan_type",
        "price",
        "billing_type",
        "employee_limit",
        "display_order",
        "is_active",
        "is_popular",
    )
    list_filter = ("plan_type", "billing_type", "is_active", "is_popular")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("display_order", "price")

    fieldsets = (
        ("Basic Info", {
            "fields": (
                "name",
                "slug",
                "plan_type",
                "billing_type",
                "price",
                "employee_limit",
                "short_tagline",
                "description",
                "badge_text",
                "is_popular",
                "is_active",
                "display_order",
            )
        }),
        ("Matrix Text Values", {
            "fields": (
                "agent_intelligence_type",
                "hiring_ats_automation",
                "onboarding_workflow",
                "employee_self_service",
                "system_integrations",
                "analytics_governance",
            )
        }),
        ("Feature Access Flags", {
            "fields": (
                "has_user_dashboard",
                "has_ai_interview_pipeline",
                "has_hr_toolkit",
                "has_ai_resume_screening",
                "has_candidate_evaluation",
                "has_hiring_workflow_automation",
                "has_interview_scheduling",
                "has_offer_letter_management",
                "has_employee_onboarding",
                "has_task_management",
                "has_team_collaboration",
                "has_email_automation",
                "has_analytics_dashboard",
                "has_custom_workflows",
                "has_api_access",
                "has_third_party_integrations",
                "has_role_based_access",
                "has_ai_hiring_agent",
                "has_autonomous_ai_agents",
                "has_predictive_ai_analytics",
                "has_priority_support",
                "has_dedicated_manager",
            )
        }),
        ("Extra Display Info", {
            "fields": ("highlights",)
        }),
    )

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "start_date", "end_date", "auto_renew")
    search_fields = ("user__email", "plan__name", "payment_reference")
    list_filter = ("status", "plan", "auto_renew")
    raw_id_fields = ("user",)


@admin.register(ManualPayment)
class ManualPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "user_email",
        "plan",
        "transaction_id",
        "bank_name",
        "payment_method",
        "payment_type",
        "upgrade_upi_or_phone",
        "status",
        "created_at",
    )
    list_filter = ("status", "payment_type", "payment_method", "plan")
    search_fields = ("user__email", "transaction_id", "bank_name", "notes")
    raw_id_fields = ("user", "subscription", "plan")
    readonly_fields = ("created_at", "updated_at", "screenshot_preview")
    ordering = ("-created_at",)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "User Email"

    def screenshot_preview(self, obj):
        if obj.screenshot:
            from django.utils.html import format_html
            url = obj.screenshot
            if url.lower().endswith(('.pdf', '.pdf')):
                return format_html('<a href="{}" target="_blank" style="font-weight: bold; color: #0a66c2;">📄 View PDF Transaction Proof</a>', url)
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="max-height: 400px; max-width: 100%; border: 1px solid #ccc; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);" />'
                '</a>', 
                url, 
                url
            )
        return "No screenshot uploaded"
    screenshot_preview.short_description = "Screenshot Preview (Click to Expand)"

    fieldsets = (
        ("Verification Info", {
            "fields": (
                "user",
                "subscription",
                "plan",
                "status",
                "notes",
            )
        }),
        ("Transaction Details", {
            "fields": (
                "transaction_id",
                "bank_name",
                "payment_method",
                "payment_type",
                "upgrade_upi_or_phone",
                "screenshot",
                "screenshot_preview",
            )
        }),
        ("System Timestamps", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

