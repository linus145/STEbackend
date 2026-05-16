from rest_framework import serializers
from .models import ProctoringSession, ViolationLog

class ViolationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ViolationLog
        fields = '__all__'

class ProctoringSessionSerializer(serializers.ModelSerializer):
    violations = ViolationLogSerializer(many=True, read_only=True)
    violation_count = serializers.IntegerField(source='violations.count', read_only=True)
    
    class Meta:
        model = ProctoringSession
        fields = ['id', 'session', 'is_active', 'integrity_score', 'violation_count', 'violations', 'created_at', 'updated_at']
