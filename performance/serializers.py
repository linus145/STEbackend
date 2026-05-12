from rest_framework import serializers
from performance.models import KPI, Goal, PerformanceReview, EmployeeFeedback
from employees.serializers import EmployeeSerializer

class KPISerializer(serializers.ModelSerializer):
    class Meta:
        model = KPI
        fields = '__all__'
        read_only_fields = ['id']

class GoalSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeSerializer(source='employee', read_only=True)
    kpi_detail = KPISerializer(source='kpi', read_only=True)
    
    class Meta:
        model = Goal
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

class PerformanceReviewSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeSerializer(source='employee', read_only=True)
    reviewer_detail = EmployeeSerializer(source='reviewer', read_only=True)
    
    class Meta:
        model = PerformanceReview
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

class EmployeeFeedbackSerializer(serializers.ModelSerializer):
    provider_detail = EmployeeSerializer(source='provider', read_only=True)
    
    class Meta:
        model = EmployeeFeedback
        fields = '__all__'
        read_only_fields = ['id', 'created_at']
