from django.contrib import admin
from payroll.models import Allowance, Deduction, SalaryStructure, Payroll, Payslip, EmployeeAllowance, EmployeeDeduction

class EmployeeAllowanceInline(admin.TabularInline):
    model = EmployeeAllowance
    extra = 1

class EmployeeDeductionInline(admin.TabularInline):
    model = EmployeeDeduction
    extra = 1

@admin.register(SalaryStructure)
class SalaryStructureAdmin(admin.ModelAdmin):
    list_display = ('employee', 'basic_salary')
    inlines = [EmployeeAllowanceInline, EmployeeDeductionInline]

@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = ('month', 'year', 'startup', 'status')
    list_filter = ('startup', 'status', 'year')

@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ('employee', 'payroll', 'net_salary', 'is_published')
    list_filter = ('payroll', 'is_published')

admin.site.register(Allowance)
admin.site.register(Deduction)
