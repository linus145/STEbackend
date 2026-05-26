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
    list_filter = ('is_deleted',)
    list_editable = ('is_deleted',)
    list_display = ('employee', 'basic_salary', 'hra', 'overtime_rate', 'status', 'is_deleted')
    inlines = [EmployeeAllowanceInline, EmployeeDeductionInline]
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__employee_id')

@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('month', 'year', 'startup', 'status', 'processed_at', 'is_deleted')
    list_filter = ('startup', 'status', 'year', 'is_deleted')
    search_fields = ('startup__name',)

@admin.register(PayrollRecord)
class PayrollRecordAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('employee', 'payroll_cycle', 'gross_salary', 'deductions', 'net_salary', 'status', 'is_deleted')
    list_filter = ('status', 'payroll_cycle__year', 'payroll_cycle__month', 'is_deleted')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__employee_id')

@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('employee', 'payroll', 'net_salary', 'is_published', 'is_deleted')
    list_filter = ('payroll', 'is_published', 'is_deleted')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__employee_id')

@admin.register(Reimbursement)
class ReimbursementAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('employee', 'category', 'amount', 'approval_status', 'created_at', 'is_deleted')
    list_filter = ('approval_status', 'category', 'is_deleted')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__employee_id')

@admin.register(PayrollAdjustment)
class PayrollAdjustmentAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('employee', 'type', 'amount', 'reason', 'payroll_cycle', 'is_deleted')
    list_filter = ('type', 'is_deleted')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__employee_id')

@admin.register(TaxConfiguration)
class TaxConfigurationAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('slab_name', 'percentage', 'min_amount', 'max_amount', 'startup', 'is_deleted')
    list_filter = ('startup', 'is_deleted')
    search_fields = ('slab_name',)

@admin.register(PayrollSetting)
class PayrollSettingAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('startup', 'currency', 'pf_percentage', 'esi_percentage', 'automation_enabled', 'is_deleted')
    list_filter = ('currency', 'automation_enabled', 'is_deleted')
    search_fields = ('startup__name',)

@admin.register(Allowance)
class AllowanceAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_taxable', 'startup', 'is_deleted')
    list_editable = ('is_deleted',)
    list_filter = ('is_taxable', 'is_deleted')

@admin.register(Deduction)
class DeductionAdmin(admin.ModelAdmin):
    list_display = ('name', 'startup', 'is_deleted')
    list_editable = ('is_deleted',)
    list_filter = ('is_deleted',)

