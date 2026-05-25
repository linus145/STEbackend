from rest_framework import serializers
from agentsettings.models import AgentSettings, AgentScheduling

class AgentSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentSettings
        fields = ['id', 'llm_model', 'temperature', 'max_iterations', 'system_prompt', 'autonomy_level']

class AgentSchedulingSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentScheduling
        fields = ['id', 'enabled', 'recurrence', 'execution_time', 'task_type', 'notification_email', 'last_executed_at', 'day_of_week', 'day_of_month', 'month_of_year']
