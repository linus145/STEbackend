from django.contrib import admin
from agentsettings.models import AgentSettings, AgentScheduling, AgentSchedulingLog

@admin.register(AgentSettings)
class AgentSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'startup', 'llm_model', 'max_iterations', 'autonomy_level')
    list_filter = ('llm_model', 'autonomy_level')
    search_fields = ('organization__name', 'startup__name', 'llm_model')

@admin.register(AgentScheduling)
class AgentSchedulingAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'startup', 'enabled', 'recurrence', 'execution_time', 'task_type', 'max_executions', 'run_count')
    list_filter = ('enabled', 'recurrence')
    search_fields = ('organization__name', 'startup__name', 'notification_email', 'command', 'task_type')

@admin.register(AgentSchedulingLog)
class AgentSchedulingLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'schedule', 'task_type', 'status', 'started_at', 'completed_at', 'duration')
    list_filter = ('status', 'task_type')
    search_fields = ('schedule__organization__name', 'schedule__startup__name', 'command', 'error_message')
