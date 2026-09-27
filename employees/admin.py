from django.contrib import admin
from employees.models import (
    Employee, EmployeeUser, EmployeeProfile, EmergencyContact, EmployeeDocument,
    EmployeeAadhaarDetail, EmployeePANDetail, EmployeeJoiningDetail,
    EmployeeBankDetail
)

@admin.register(EmployeeUser)
class EmployeeUserAdmin(admin.ModelAdmin):
    list_display = ('portal_username', 'email', 'get_employee_name', 'role', 'is_active', 'last_login', 'created_at')
    search_fields = ('portal_username', 'email', 'employee__first_name', 'employee__last_name', 'employee__employee_id')
    list_filter = ('role', 'is_active')
    readonly_fields = ('created_at', 'updated_at', 'last_login')

    def get_employee_name(self, obj):
        if hasattr(obj, 'employee') and obj.employee:
            return f"{obj.employee.first_name} {obj.employee.last_name} ({obj.employee.employee_id})"
        return "-"
    get_employee_name.short_description = "Employee"


class EmployeeProfileInline(admin.StackedInline):
    model = EmployeeProfile
    can_delete = False

class EmployeeAadhaarDetailInline(admin.StackedInline):
    model = EmployeeAadhaarDetail
    can_delete = False

class EmployeePANDetailInline(admin.StackedInline):
    model = EmployeePANDetail
    can_delete = False

class EmployeeJoiningDetailInline(admin.StackedInline):
    model = EmployeeJoiningDetail
    can_delete = False

class EmployeeBankDetailInline(admin.StackedInline):
    model = EmployeeBankDetail
    can_delete = False

class EmergencyContactInline(admin.TabularInline):
    model = EmergencyContact
    extra = 1

class EmployeeDocumentInline(admin.TabularInline):
    model = EmployeeDocument
    extra = 1

class EmployeeUserInline(admin.StackedInline):
    model = EmployeeUser
    can_delete = False
    extra = 0
    readonly_fields = ('last_login', 'created_at', 'updated_at')

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('employee_id', 'first_name', 'last_name', 'startup', 'department', 'designation', 'status', 'is_deleted')
    search_fields = ('employee_id', 'first_name', 'last_name', 'email')
    list_filter = ('startup', 'status', 'employment_type', 'department', 'is_deleted')
    readonly_fields = ('user',)
    inlines = [
        EmployeeUserInline,
        EmployeeProfileInline, 
        EmergencyContactInline, 
        EmployeeDocumentInline,
        EmployeeAadhaarDetailInline,
        EmployeePANDetailInline,
        EmployeeJoiningDetailInline,
        EmployeeBankDetailInline
    ]

@admin.register(EmployeeAadhaarDetail)
class EmployeeAadhaarDetailAdmin(admin.ModelAdmin):
    list_display = ('employee', 'organization', 'aadhaar_number', 'verified')
    list_filter = ('verified', 'organization')

@admin.register(EmployeePANDetail)
class EmployeePANDetailAdmin(admin.ModelAdmin):
    list_display = ('employee', 'organization', 'pan_number', 'verified')
    list_filter = ('verified', 'organization')

@admin.register(EmployeeJoiningDetail)
class EmployeeJoiningDetailAdmin(admin.ModelAdmin):
    list_display = ('employee', 'organization', 'joining_date', 'probation_period', 'confirmation_date')
    list_filter = ('organization',)

@admin.register(EmployeeBankDetail)
class EmployeeBankDetailAdmin(admin.ModelAdmin):
    list_display = ('employee', 'organization', 'bank_name', 'account_number', 'ifsc_code')
    list_filter = ('organization',)
