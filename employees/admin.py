from django.contrib import admin
from employees.models import Employee, EmployeeProfile, EmergencyContact, EmployeeDocument

class EmployeeProfileInline(admin.StackedInline):
    model = EmployeeProfile
    can_delete = False

class EmergencyContactInline(admin.TabularInline):
    model = EmergencyContact
    extra = 1

class EmployeeDocumentInline(admin.TabularInline):
    model = EmployeeDocument
    extra = 1

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'first_name', 'last_name', 'startup', 'department', 'designation', 'status')
    search_fields = ('employee_id', 'first_name', 'last_name', 'email')
    list_filter = ('startup', 'status', 'employment_type', 'department')
    inlines = [EmployeeProfileInline, EmergencyContactInline, EmployeeDocumentInline]
