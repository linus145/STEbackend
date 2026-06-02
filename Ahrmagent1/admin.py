from django.contrib import admin
from Ahrmagent1.models import (
    AgentGoal,
    AgentExecution,
    AgentMemory,
    AgentDecision,
    AgentAction,
    AgentLog,
    AgentSchedule,
    AgentCheckpoint,
    AgentChatHistory
)

@admin.register(AgentGoal)
class AgentGoalAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'startup', 'goal_type', 'status', 'priority', 'created_at', 'completed_at')
    list_filter = ('status', 'priority', 'goal_type', 'organization', 'startup', 'created_at')
    search_fields = ('id', 'goal')
    readonly_fields = ('created_at', 'updated_at', 'completed_at')
    ordering = ('-created_at',)

@admin.register(AgentExecution)
class AgentExecutionAdmin(admin.ModelAdmin):
    list_display = ('id', 'goal', 'organization', 'startup', 'agent_type', 'status', 'execution_version', 'started_at', 'completed_at')
    list_filter = ('status', 'agent_type', 'organization', 'startup', 'started_at')
    search_fields = ('id', 'goal__goal', 'agent_type')
    readonly_fields = ('started_at', 'completed_at')
    ordering = ('-started_at',)

@admin.register(AgentMemory)
class AgentMemoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'execution', 'memory_type', 'memory_key', 'created_at')
    list_filter = ('memory_type', 'created_at')
    search_fields = ('execution__id', 'memory_key')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

@admin.register(AgentDecision)
class AgentDecisionAdmin(admin.ModelAdmin):
    list_display = ('id', 'execution', 'decision_type', 'created_at')
    list_filter = ('decision_type', 'created_at')
    search_fields = ('execution__id', 'decision_type')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

@admin.register(AgentAction)
class AgentActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'execution', 'action_type', 'created_at')
    list_filter = ('action_type', 'created_at')
    search_fields = ('execution__id', 'action_type')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

@admin.register(AgentLog)
class AgentLogAdmin(admin.ModelAdmin):
    list_display = ('execution', 'level', 'log_level', 'timestamp', 'created_at')
    list_filter = ('level', 'log_level', 'timestamp')
    search_fields = ('execution__id', 'message')
    readonly_fields = ('timestamp', 'created_at')
    ordering = ('-timestamp',)

@admin.register(AgentSchedule)
class AgentScheduleAdmin(admin.ModelAdmin):
    list_display = ('id', 'goal', 'organization', 'startup', 'schedule_type', 'schedule_expression', 'next_run', 'status')
    list_filter = ('schedule_type', 'status', 'organization', 'startup')
    search_fields = ('goal__goal', 'schedule_expression')
    readonly_fields = ('next_run',)

@admin.register(AgentCheckpoint)
class AgentCheckpointAdmin(admin.ModelAdmin):
    list_display = ('id', 'execution', 'created_at')
    search_fields = ('execution__id',)
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

@admin.register(AgentChatHistory)
class AgentChatHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'sender', 'timestamp')
    list_filter = ('sender', 'timestamp')
    search_fields = ('user__id', 'text')
    readonly_fields = ('timestamp',)
    ordering = ('-timestamp',)
