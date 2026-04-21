from django.contrib import admin
from .models import Founder

@admin.register(Founder)
class FounderAdmin(admin.ModelAdmin):
    list_display = ('get_email', 'get_full_name', 'primary_industry', 'experience_years', 'location')
    list_filter = ('primary_industry', 'location')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'headline')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {
            'fields': ('user', 'headline', 'profile_image_url', 'location')
        }),
        ('Professional Info', {
            'fields': ('bio', 'primary_industry', 'experience_years', 'skills')
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