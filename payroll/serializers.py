from rest_framework import serializers
from payroll.models import (
    Allowance, Deduction, SalaryStructure, Payroll, PayrollRecord, 
    Payslip, EmployeeAllowance, EmployeeDeduction, Reimbursement, 
    PayrollAdjustment, TaxConfiguration, PayrollSetting, DocumentTemplate
)
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

def resolve_employee_id_in_data(data):
    if 'employee' in data:
        emp_val = data['employee']
        if emp_val:
            emp_val = str(emp_val).strip()
            import uuid
            is_uuid = False
            try:
                uuid.UUID(emp_val)
                is_uuid = True
            except ValueError:
                pass
            
            if not is_uuid:
                from employees.models import Employee
                emp_obj = Employee.all_objects.filter(employee_id=emp_val).first()
                if emp_obj:
                    if hasattr(data, 'copy'):
                        data = data.copy()
                    data['employee'] = str(emp_obj.id)
                else:
                    raise serializers.ValidationError({
                        'employee': f"Employee with ID '{emp_val}' does not exist."
                    })
    return data

from django.utils import timezone
import datetime

class SalaryStructureSerializer(serializers.ModelSerializer):
    employee_allowances = EmployeeAllowanceSerializer(source='employeeallowance_set', many=True, read_only=True)
    employee_deductions = EmployeeDeductionSerializer(source='employeededuction_set', many=True, read_only=True)
    
    employee_name = serializers.SerializerMethodField()
    employee_last_name = serializers.SerializerMethodField()
    employee_code = serializers.SerializerMethodField()
    employee_designation = serializers.SerializerMethodField()
    is_employee_deleted = serializers.SerializerMethodField()
    effective_from = serializers.DateField(default=timezone.now().date)
    
    class Meta:
        model = SalaryStructure
        fields = [
            'id', 'employee', 'employee_code', 'employee_name', 'employee_last_name', 'employee_designation', 'is_employee_deleted', 'basic_salary', 'hra', 
            'overtime_rate', 'tax_percentage', 'pf_percentage', 'esi_percentage', 
            'effective_from', 'status', 'employee_allowances', 'employee_deductions', 
            'created_at', 'updated_at'
        ]

    def _get_employee(self, obj):
        from employees.models import Employee
        return Employee.all_objects.filter(id=obj.employee_id).first()

    def get_employee_name(self, obj):
        emp = self._get_employee(obj)
        return emp.first_name if emp else None

    def get_employee_last_name(self, obj):
        emp = self._get_employee(obj)
        return emp.last_name if emp else None

    def get_employee_code(self, obj):
        emp = self._get_employee(obj)
        return emp.employee_id if emp else None

    def get_employee_designation(self, obj):
        emp = self._get_employee(obj)
        if emp and emp.designation:
            return emp.designation.title
        return 'Team Member'

    def get_is_employee_deleted(self, obj):
        emp = self._get_employee(obj)
        return emp.is_deleted if emp else True

    def to_internal_value(self, data):
        resolved_data = resolve_employee_id_in_data(data)
        return super().to_internal_value(resolved_data)

    def to_representation(self, instance):
        if hasattr(instance, 'effective_from') and isinstance(instance.effective_from, datetime.datetime):
            instance.effective_from = instance.effective_from.date()
        return super().to_representation(instance)

class PayrollAdjustmentSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.first_name', read_only=True)
    employee_last_name = serializers.CharField(source='employee.last_name', read_only=True)

    class Meta:
        model = PayrollAdjustment
        fields = '__all__'

    def to_internal_value(self, data):
        resolved_data = resolve_employee_id_in_data(data)
        return super().to_internal_value(resolved_data)

class ReimbursementSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.first_name', read_only=True)
    employee_last_name = serializers.CharField(source='employee.last_name', read_only=True)

    class Meta:
        model = Reimbursement
        fields = '__all__'

    def to_internal_value(self, data):
        resolved_data = resolve_employee_id_in_data(data)
        return super().to_internal_value(resolved_data)

class TaxConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxConfiguration
        fields = '__all__'

class PayrollRecordSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeSerializer(source='employee', read_only=True)
    
    class Meta:
        model = PayrollRecord
        fields = '__all__'

class PayrollSerializer(serializers.ModelSerializer):
    records_count = serializers.IntegerField(source='records.count', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.username', read_only=True)
    
    class Meta:
        model = Payroll
        fields = [
            'id', 'startup', 'month', 'year', 'status', 'processed_at', 
            'approved_by', 'approved_by_name', 'records_count'
        ]

class PayslipSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeSerializer(source='employee', read_only=True)
    payroll_detail = PayrollSerializer(source='payroll', read_only=True)
    
    class Meta:
        model = Payslip
        fields = '__all__'

class PayrollSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollSetting
        fields = '__all__'


class DocumentTemplateSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = DocumentTemplate
        fields = [
            'id', 'startup', 'name', 'category', 'category_display', 
            'content', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'startup', 'created_at', 'updated_at']
