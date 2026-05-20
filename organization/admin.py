from django.contrib import admin
from organization.models import Department, Designation, Organization

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'startup', 'tax_id', 'created_at')
    search_fields = ('name', 'tax_id', 'company__company_name', 'startup__name')
    list_filter = ('startup', 'created_at')

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'startup', 'created_at')
    search_fields = ('name', 'startup__name')
    list_filter = ('startup',)

@admin.register(Designation)
class DesignationAdmin(admin.ModelAdmin):
    list_display = ('title', 'startup', 'created_at')
    search_fields = ('title', 'startup__name')
    list_filter = ('startup',)
