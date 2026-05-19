from django.contrib import admin
from Ahrmagent1.models import AgentExecution, AgentLog, AgentChatHistory


@admin.register(AgentExecution)
class AgentExecutionAdmin(admin.ModelAdmin):
    list_display = ('id', 'agent_type', 'status', 'started_at', 'completed_at')
    list_filter = ('status', 'started_at')
    search_fields = ('id', 'agent_type')
    readonly_fields = ('started_at', 'completed_at')

@admin.register(AgentLog)
class AgentLogAdmin(admin.ModelAdmin):
    list_display = ('execution', 'level', 'timestamp')
    list_filter = ('level', 'timestamp')
    search_fields = ('execution__id', 'message')
    readonly_fields = ('timestamp',)
    ordering = ('-timestamp',)

@admin.register(AgentChatHistory)
class AgentChatHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'sender', 'timestamp')
    list_filter = ('sender', 'timestamp')
    search_fields = ('user__id', 'text')
    readonly_fields = ('timestamp',)
    ordering = ('-timestamp',)
