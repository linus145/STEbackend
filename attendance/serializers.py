from rest_framework import serializers
from attendance.models import Shift, Attendance, WorkSession
from employees.serializers import EmployeeSerializer

class ShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shift
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

class WorkSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkSession
        fields = '__all__'
        read_only_fields = ['id']

class AttendanceSerializer(serializers.ModelSerializer):
    sessions = WorkSessionSerializer(many=True, read_only=True)
    employee_detail = EmployeeSerializer(source='employee', read_only=True)
    
    class Meta:
        model = Attendance
        fields = [
            'id', 'startup', 'employee', 'employee_detail', 'date', 
            'status', 'total_work_hours', 'is_late', 'sessions', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
