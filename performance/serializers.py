from rest_framework import serializers
from performance.models import KPI, Goal, PerformanceReview, EmployeeFeedback, PerformanceScoreBreakdown, PerformanceCycle, Competency, CompetencyScore
from employees.serializers import EmployeeSerializer

class PerformanceCycleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceCycle
        fields = '__all__'
        read_only_fields = ['id', 'organization']

class CompetencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Competency
        fields = '__all__'
        read_only_fields = ['id', 'organization']

class CompetencyScoreSerializer(serializers.ModelSerializer):
    competency_detail = CompetencySerializer(source='competency', read_only=True)
    class Meta:
        model = CompetencyScore
        fields = '__all__'
        read_only_fields = ['id']

class KPISerializer(serializers.ModelSerializer):
    class Meta:
        model = KPI
        fields = '__all__'
        read_only_fields = ['id', 'organization']

class GoalSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeSerializer(source='employee', read_only=True)
    kpi_detail = KPISerializer(source='kpi', read_only=True)
    
    class Meta:
        model = Goal
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'organization']

class PerformanceScoreBreakdownSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceScoreBreakdown
        fields = '__all__'
        read_only_fields = ['id']

class PerformanceReviewSerializer(serializers.ModelSerializer):
    employee_detail = EmployeeSerializer(source='employee', read_only=True)
    reviewer_detail = EmployeeSerializer(source='reviewer', read_only=True)
    score_breakdown = PerformanceScoreBreakdownSerializer(read_only=True)
    cycle_detail = PerformanceCycleSerializer(source='cycle', read_only=True)
    
    class Meta:
        model = PerformanceReview
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'organization']

class EmployeeFeedbackSerializer(serializers.ModelSerializer):
    provider_detail = EmployeeSerializer(source='provider', read_only=True)
    
    class Meta:
        model = EmployeeFeedback
        fields = '__all__'
        read_only_fields = ['id', 'created_at']
