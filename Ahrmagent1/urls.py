from django.urls import path
from Ahrmagent1.views import (
    AgentRunView,
    AgentExecutionDetailView,
    AgentPlanView,
    LLMThinkView,
    AgentExecutionListView,
    AgentChatHistoryView,
    AgentChatHistoryClearView,
    AgentGoalListView,
    AgentActiveExecutionView,
    AgentMemoryView,
    AgentDecisionView,
    AgentActionView,
    AgentCheckpointView,
    AgentScheduleView,
)

urlpatterns = [
    path('run/', AgentRunView.as_view(), name='agent-run'),
    path('plan/', AgentPlanView.as_view(), name='agent-plan'),
    path('executions/', AgentExecutionListView.as_view(), name='agent-executions'),
    path('executions/active/', AgentActiveExecutionView.as_view(), name='agent-active-execution'),
    path('executions/<uuid:pk>/', AgentExecutionDetailView.as_view(), name='agent-execution-detail'),
    path('executions/<uuid:execution_id>/memories/', AgentMemoryView.as_view(), name='agent-execution-memories'),
    path('executions/<uuid:execution_id>/decisions/', AgentDecisionView.as_view(), name='agent-execution-decisions'),
    path('executions/<uuid:execution_id>/actions/', AgentActionView.as_view(), name='agent-execution-actions'),
    path('executions/<uuid:execution_id>/checkpoints/', AgentCheckpointView.as_view(), name='agent-execution-checkpoints'),
    path('goals/', AgentGoalListView.as_view(), name='agent-goals'),
    path('schedules/', AgentScheduleView.as_view(), name='agent-schedules'),
    path('llm/think/', LLMThinkView.as_view(), name='llm-think'),
    path('chat/history/', AgentChatHistoryView.as_view(), name='agent-chat-history'),
    path('chat/clear/', AgentChatHistoryClearView.as_view(), name='agent-chat-clear'),
]