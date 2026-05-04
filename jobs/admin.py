from django.contrib import admin
from .models import JobPost, JobApplication, Skill, AppliedJob

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "created_at")
    list_filter = ("category",)
    search_fields = ("name",)

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

@admin.register(AppliedJob)
class AppliedJobAdmin(admin.ModelAdmin):
    list_display = ("job_name", "applicant_id", "applied_at")
    search_fields = ("job_name", "applicant_id", "job_id")
    readonly_fields = ("id", "applied_at")
