from django.contrib import admin
from django.db import models
from django.forms import Textarea
from .models import AboutUs, MissionPrinciple, Blog, JobOpening, ContactInquiry, ContactSales, Careers

@admin.register(AboutUs)
class AboutUsAdmin(admin.ModelAdmin):
    list_display = ('title', 'updated_at')

@admin.register(MissionPrinciple)
class MissionPrincipleAdmin(admin.ModelAdmin):
    list_display = ('title', 'order')
    list_editable = ('order',)

@admin.register(Blog)
class BlogAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'date')
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ('title', 'content', 'author')

@admin.register(JobOpening)
class JobOpeningAdmin(admin.ModelAdmin):
    list_display = ('role', 'department', 'location', 'is_active')
    list_filter = ('department', 'is_active')
    search_fields = ('role', 'description')
    formfield_overrides = {
        models.TextField: {
            'widget': Textarea(
                attrs={
                    'rows': 15,
                    'cols': 80,
                    'style': 'font-family: monospace; font-size: 14px; padding: 10px; width: 100%; max-width: 800px; border-radius: 4px;',
                    'placeholder': 'Type description here. Supports Markdown:\n### About the Role\nWe are looking for...\n\n### Key Responsibilities\n- Bullet point 1\n- Bullet point 2\n\n**Bold Text**'
                }
            )
        },
    }

@admin.register(Careers)
class CareersAdmin(admin.ModelAdmin):
    list_display = ('role', 'department', 'location', 'is_active')
    list_filter = ('department', 'is_active')
    search_fields = ('role', 'description')
    formfield_overrides = {
        models.TextField: {
            'widget': Textarea(
                attrs={
                    'rows': 15,
                    'cols': 80,
                    'style': 'font-family: monospace; font-size: 14px; padding: 10px; width: 100%; max-width: 800px; border-radius: 4px;',
                    'placeholder': 'Type description here. Supports Markdown:\n### About the Role\nWe are looking for...\n\n### Key Responsibilities\n- Bullet point 1\n- Bullet point 2\n\n**Bold Text**'
                }
            )
        },
    }

@admin.register(ContactInquiry)
class ContactInquiryAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'subject', 'created_at')
    readonly_fields = ('full_name', 'email', 'subject', 'message', 'created_at')
    search_fields = ('full_name', 'email', 'subject')

@admin.register(ContactSales)
class ContactSalesAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'company_name', 'company_size', 'phone_number', 'created_at')
    readonly_fields = ('full_name', 'email', 'company_name', 'company_size', 'phone_number', 'message', 'created_at')
    search_fields = ('full_name', 'email', 'company_name')
    list_filter = ('company_size', 'created_at')

