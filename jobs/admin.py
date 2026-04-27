from django.contrib import admin
from .models import JobPost, JobApplication
@admin.register(JobPost)
class JobPostAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "job_type", "work_mode", "status", "experience_level", "created_at")
    list_filter = ("status", "job_type", "work_mode", "experience_level", "is_deleted")
    search_fields = ("title", "company__company_name", "description")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("company",)


@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display = ("applicant", "job", "status", "applied_at")
    list_filter = ("status", "is_deleted")
    search_fields = ("applicant__email", "job__title")
    readonly_fields = ("id", "applied_at", "updated_at")
    raw_id_fields = ("job", "applicant")
