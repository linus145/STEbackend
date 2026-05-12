from rest_framework import serializers
from Ahrmagent1.models import AgentExecution, AgentLog

class AgentLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentLog
        fields = ['timestamp', 'level', 'message', 'action']

class AgentExecutionSerializer(serializers.ModelSerializer):
    logs = AgentLogSerializer(many=True, read_only=True)
    
    class Meta:
        model = AgentExecution
        fields = [
            'id', 'agent_type', 'status', 'started_at', 
            'completed_at', 'execution_time', 'screenshot', 
            'actions_performed', 'metadata', 'logs'
        ]

class AgentRunRequestSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    url = serializers.URLField(required=False, allow_null=True)
    handover = serializers.BooleanField(required=False, default=False)
    task_type = serializers.CharField(max_length=50, required=False)
    job_id = serializers.CharField(max_length=100, required=False)
    target_count = serializers.IntegerField(required=False, default=5)
