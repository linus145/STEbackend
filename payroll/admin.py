from django.contrib import admin
from payroll.models import (
    Allowance, Deduction, SalaryStructure, Payroll, Payslip, 
    EmployeeAllowance, EmployeeDeduction, Reimbursement, 
    PayrollAdjustment, TaxConfiguration, PayrollSetting, PayrollRecord
)

class EmployeeAllowanceInline(admin.TabularInline):
    model = EmployeeAllowance
    extra = 1

class EmployeeDeductionInline(admin.TabularInline):
    model = EmployeeDeduction
    extra = 1

@admin.register(SalaryStructure)
class SalaryStructureAdmin(admin.ModelAdmin):
    list_display = ('employee', 'basic_salary', 'hra', 'overtime_rate', 'status')
    inlines = [EmployeeAllowanceInline, EmployeeDeductionInline]
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__employee_id')

@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = ('month', 'year', 'startup', 'status', 'processed_at')
    list_filter = ('startup', 'status', 'year')
    search_fields = ('startup__name',)

@admin.register(PayrollRecord)
class PayrollRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'payroll_cycle', 'gross_salary', 'deductions', 'net_salary', 'status')
    list_filter = ('status', 'payroll_cycle__year', 'payroll_cycle__month')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__employee_id')

@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ('employee', 'payroll', 'net_salary', 'is_published')
    list_filter = ('payroll', 'is_published')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__employee_id')

@admin.register(Reimbursement)
class ReimbursementAdmin(admin.ModelAdmin):
    list_display = ('employee', 'category', 'amount', 'approval_status', 'created_at')
    list_filter = ('approval_status', 'category')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__employee_id')

@admin.register(PayrollAdjustment)
class PayrollAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('employee', 'type', 'amount', 'reason', 'payroll_cycle')
    list_filter = ('type',)
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__employee_id')

@admin.register(TaxConfiguration)
class TaxConfigurationAdmin(admin.ModelAdmin):
    list_display = ('slab_name', 'percentage', 'min_amount', 'max_amount', 'startup')
    list_filter = ('startup',)
    search_fields = ('slab_name',)

@admin.register(PayrollSetting)
class PayrollSettingAdmin(admin.ModelAdmin):
    list_display = ('startup', 'currency', 'pf_percentage', 'esi_percentage', 'automation_enabled')
    list_filter = ('currency', 'automation_enabled')
    search_fields = ('startup__name',)

admin.site.register(Allowance)
admin.site.register(Deduction)
