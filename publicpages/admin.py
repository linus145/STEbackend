from django.contrib import admin
from .models import AboutUs, MissionPrinciple, Blog, JobOpening, ContactInquiry

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

@admin.register(ContactInquiry)
class ContactInquiryAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'subject', 'created_at')
    readonly_fields = ('full_name', 'email', 'subject', 'message', 'created_at')
    search_fields = ('full_name', 'email', 'subject')
