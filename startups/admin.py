from django.contrib import admin
from .models import Startup, CompanyProfile

@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ("company_name", "owner", "industry", "company_size", "location", "is_approved", "is_genuine", "created_at")
    list_filter = ("is_approved", "is_genuine", "industry", "company_size", "is_deleted")
    search_fields = ("company_name", "owner__email", "industry")
    readonly_fields = ("id", "created_at", "updated_at")
    raw_id_fields = ("owner",)

@admin.register(Startup)
class StartupAdmin(admin.ModelAdmin):
    list_display = ('name', 'industry', 'stage', 'get_founder_email', 'seeking_amount')
    list_filter = ('industry', 'stage')
    search_fields = ('name', 'pitch', 'founder__email')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('founder', 'name', 'logo_url', 'website_url')
        }),
        ('Pitch & Industry', {
            'fields': ('pitch', 'industry', 'stage')
        }),
        ('Funding', {
            'fields': ('seeking_amount',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def get_founder_email(self, obj):
        return obj.founder.email
    get_founder_email.short_description = 'Founder Email'
