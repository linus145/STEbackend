from rest_framework import serializers
from leave_management.models import LeaveType, LeaveRequest, LeaveBalance
from employees.serializers import EmployeeSerializer

class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = '__all__'
        read_only_fields = ['id']

class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeSerializer(source='employee', read_only=True)
    leave_type_detail = LeaveTypeSerializer(source='leave_type', read_only=True)
    
    class Meta:
        model = LeaveRequest
        fields = '__all__'
        read_only_fields = ['id', 'status', 'approved_by', 'comment', 'created_at', 'updated_at']

class LeaveBalanceSerializer(serializers.ModelSerializer):
    leave_type_name = serializers.CharField(source='leave_type.name', read_only=True)
    
    class Meta:
        model = LeaveBalance
        fields = ['id', 'employee', 'leave_type', 'leave_type_name', 'year', 'total_days', 'used_days', 'remaining_days']
        read_only_fields = ['id', 'remaining_days']
