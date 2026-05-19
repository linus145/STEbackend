from django.contrib import admin
from employees.models import (
    Employee, EmployeeProfile, EmergencyContact, EmployeeDocument,
    EmployeeAadhaarDetail, EmployeePANDetail, EmployeeJoiningDetail,
    EmployeeBankDetail
)

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

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'first_name', 'last_name', 'startup', 'department', 'designation', 'status')
    search_fields = ('employee_id', 'first_name', 'last_name', 'email')
    list_filter = ('startup', 'status', 'employment_type', 'department')
    inlines = [
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
