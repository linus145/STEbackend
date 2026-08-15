from django.contrib import admin
from .models import UserCredit, CreditTransaction, ManualCreditVerification

@admin.register(UserCredit)
class UserCreditAdmin(admin.ModelAdmin):
    list_display = ("user", "balance", "last_allocated_plan_type", "updated_at")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    list_filter = ("last_allocated_plan_type",)
    readonly_fields = ("created_at", "updated_at")

@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "activity_type", "module", "candidate_id", "interview_id", "job_id", "action_type", "created_at")
    search_fields = ("user__email", "user__first_name", "user__last_name", "description", "module", "candidate_id", "interview_id", "job_id", "action_type")
    list_filter = ("activity_type", "module", "action_type", "created_at")
    readonly_fields = ("created_at",)

@admin.register(ManualCreditVerification)
class ManualCreditVerificationAdmin(admin.ModelAdmin):
    list_display = ("user", "package_name", "credits_requested", "transaction_id", "payment_method", "status", "screenshot_thumbnail", "created_at")
    search_fields = ("user__email", "transaction_id", "package_name", "upi_or_phone")
    list_filter = ("status", "payment_method", "created_at")
    readonly_fields = ("created_at", "updated_at", "screenshot_preview")
    actions = ["approve_verifications", "reject_verifications"]

    fieldsets = (
        ("Verification Info", {
            "fields": (
                "user",
                "package_name",
                "credits_requested",
                "amount_paid",
                "status",
                "notes",
            )
        }),
        ("Payment & Screenshot Proof", {
            "fields": (
                "transaction_id",
                "payment_method",
                "upi_or_phone",
                "screenshot",
                "screenshot_preview",
            )
        }),
        ("Timestamps", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    def screenshot_thumbnail(self, obj):
        if obj.screenshot:
            from django.utils.html import format_html
            url = obj.screenshot
            return format_html(
                '<a href="{}" target="_blank">'
                '<img src="{}" style="height: 40px; width: 60px; object-fit: cover; border-radius: 3px; border: 1px solid #ccc;" />'
                '</a>',
                url,
                url
            )
        return "—"
    screenshot_thumbnail.short_description = "Proof Image"

    def screenshot_preview(self, obj):
        if obj.screenshot:
            from django.utils.html import format_html
            url = obj.screenshot
            return format_html(
                '<div style="margin-top: 5px;">'
                '<a href="{}" target="_blank" style="display: inline-block; margin-bottom: 8px; font-weight: bold; color: #0a66c2;">🔗 Open Full Image in New Tab</a><br/>'
                '<a href="{}" target="_blank">'
                '<img src="{}" style="max-height: 380px; max-width: 550px; border: 1px solid #ccc; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);" />'
                '</a>'
                '</div>',
                url,
                url,
                url
            )
        return "No screenshot uploaded"
    screenshot_preview.short_description = "Screenshot Preview"

    @admin.action(description="Approve selected credit payment verifications and allocate credits")
    def approve_verifications(self, request, queryset):
        count = 0
        for obj in queryset.filter(status="pending"):
            obj.status = "approved"
            obj.save()
            count += 1
        self.message_user(request, f"Successfully approved {count} credit payment verifications.")

    @admin.action(description="Reject selected credit payment verifications")
    def reject_verifications(self, request, queryset):
        count = queryset.filter(status="pending").update(status="rejected")
        self.message_user(request, f"Successfully rejected {count} credit payment verifications.")
