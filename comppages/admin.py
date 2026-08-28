from django.contrib import admin
from .models import CompanyPage, CompanyPost


@admin.register(CompanyPage)
class CompanyPageAdmin(admin.ModelAdmin):
    list_display = ("slug", "get_company_name", "page_type", "is_verified", "created_at")
    search_fields = ("slug", "company__company_name", "tagline")
    list_filter = ("page_type", "is_verified", "created_at")
    prepopulated_fields = {"slug": ("tagline",)}

    def get_company_name(self, obj):
        return obj.company.company_name
    get_company_name.short_description = "Company Name"


@admin.register(CompanyPost)
class CompanyPostAdmin(admin.ModelAdmin):
    list_display = ("id", "get_company_name", "author", "is_promoted", "created_at")
    search_fields = ("company_page__company__company_name", "company_page__slug", "content", "author__email")
    list_filter = ("is_promoted", "created_at")

    def get_company_name(self, obj):
        return obj.company_page.company.company_name if obj.company_page and obj.company_page.company else "-"
    get_company_name.short_description = "Company Name"
