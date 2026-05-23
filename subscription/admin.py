from django.contrib import admin
from .models import SubscriptionPlan, UserSubscription

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
