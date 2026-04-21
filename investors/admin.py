from django.contrib import admin
from .models import Investor

@admin.register(Investor)
class InvestorAdmin(admin.ModelAdmin):
    list_display = ('get_email', 'firm_name', 'location', 'get_full_name')
    list_filter = ('firm_name', 'location')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'firm_name', 'headline')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('user', 'headline', 'profile_image_url', 'location', 'firm_name')
        }),
        ('Investment Info', {
            'fields': ('bio', 'preferred_stages', 'preferred_industries', 'minimum_investment_range', 'maximum_investment_range')
        }),
        ('Social & Links', {
            'fields': ('linkedin_url', 'portfolio_url')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'

    def get_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}"
    get_full_name.short_description = 'Full Name'