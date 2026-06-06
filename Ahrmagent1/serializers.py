from rest_framework import serializers
from Ahrmagent1.models import (
    AgentGoal,
    AgentExecution,
    AgentLog,
    AgentMemory,
    AgentDecision,
    AgentAction,
    AgentSchedule,
    AgentCheckpoint,
    AgentChatHistory
)

class AgentGoalSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentGoal
        fields = '__all__'

class AgentLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentLog
        fields = ['id', 'timestamp', 'level', 'log_level', 'message', 'action', 'created_at']

class AgentMemorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentMemory
        fields = '__all__'

class AgentDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentDecision
        fields = '__all__'

class AgentActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentAction
        fields = '__all__'

class AgentScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentSchedule
        fields = '__all__'

class AgentCheckpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentCheckpoint
        fields = '__all__'

class AgentExecutionSerializer(serializers.ModelSerializer):
    logs = AgentLogSerializer(many=True, read_only=True)
    memories = AgentMemorySerializer(many=True, read_only=True)
    decisions = AgentDecisionSerializer(many=True, read_only=True)
    agent_actions = AgentActionSerializer(many=True, read_only=True)
    checkpoints = AgentCheckpointSerializer(many=True, read_only=True)
    goal_details = AgentGoalSerializer(source='goal', read_only=True)
    
    class Meta:
        model = AgentExecution
        fields = [
            'id', 'goal', 'organization', 'startup', 'agent_type', 'status', 'execution_version',
            'started_at', 'completed_at', 'execution_time', 'screenshot', 
            'actions_performed', 'metadata', 'logs', 'memories', 
            'decisions', 'agent_actions', 'checkpoints', 'goal_details'
        ]

class AgentRunRequestSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    url = serializers.URLField(required=False, allow_null=True)
    handover = serializers.BooleanField(required=False, default=False)
    task_type = serializers.CharField(max_length=50, required=False)
    job_id = serializers.CharField(max_length=100, required=False)
    target_count = serializers.IntegerField(required=False, default=5)

class AgentChatHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentChatHistory
        fields = ['id', 'sender', 'text', 'timestamp', 'conversation_id']
