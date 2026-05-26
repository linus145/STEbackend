from django.contrib import admin
from organization.models import Department, Designation, Organization

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('name', 'company', 'startup', 'tax_id', 'created_at', 'is_deleted')
    search_fields = ('name', 'tax_id', 'company__company_name', 'startup__name')
    list_filter = ('startup', 'created_at', 'is_deleted')

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('name', 'startup', 'created_at', 'is_deleted')
    search_fields = ('name', 'startup__name')
    list_filter = ('startup', 'is_deleted')

@admin.register(Designation)
class DesignationAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('title', 'startup', 'created_at', 'is_deleted')
    search_fields = ('title', 'startup__name')
    list_filter = ('startup', 'is_deleted')
