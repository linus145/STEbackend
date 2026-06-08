from django.contrib import admin
from .models import UserCredit, CreditTransaction

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
