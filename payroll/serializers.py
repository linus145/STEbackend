from rest_framework import serializers
from payroll.models import Allowance, Deduction, SalaryStructure, Payroll, Payslip, EmployeeAllowance, EmployeeDeduction
from employees.serializers import EmployeeSerializer

class AllowanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Allowance
        fields = '__all__'

class DeductionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deduction
        fields = '__all__'

class EmployeeAllowanceSerializer(serializers.ModelSerializer):
    allowance_name = serializers.CharField(source='allowance.name', read_only=True)
    class Meta:
        model = EmployeeAllowance
        fields = ['id', 'allowance', 'allowance_name', 'amount']

class EmployeeDeductionSerializer(serializers.ModelSerializer):
    deduction_name = serializers.CharField(source='deduction.name', read_only=True)
    class Meta:
        model = EmployeeDeduction
        fields = ['id', 'deduction', 'deduction_name', 'amount']

class SalaryStructureSerializer(serializers.ModelSerializer):
    employee_allowances = EmployeeAllowanceSerializer(source='employeeallowance_set', many=True, read_only=True)
    employee_deductions = EmployeeDeductionSerializer(source='employeededuction_set', many=True, read_only=True)
    
    class Meta:
        model = SalaryStructure
        fields = ['id', 'employee', 'basic_salary', 'employee_allowances', 'employee_deductions', 'created_at', 'updated_at']

class PayrollSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payroll
        fields = '__all__'

class PayslipSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeSerializer(source='employee', read_only=True)
    
    class Meta:
        model = Payslip
        fields = '__all__'
