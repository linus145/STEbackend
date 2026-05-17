from django.urls import path
from Ahrmagent1.views import (
    AgentRunView,
    AgentExecutionDetailView,
    AgentPlanView,
    LLMThinkView,
    AgentExecutionListView,
    AgentChatHistoryView,
    AgentChatHistoryClearView,
)

urlpatterns = [
    path('run/', AgentRunView.as_view(), name='agent-run'),
    path('plan/', AgentPlanView.as_view(), name='agent-plan'),
    path('executions/', AgentExecutionListView.as_view(), name='agent-executions'),
    path('executions/<uuid:pk>/', AgentExecutionDetailView.as_view(), name='agent-execution-detail'),
    path('llm/think/', LLMThinkView.as_view(), name='llm-think'),
    path('chat/history/', AgentChatHistoryView.as_view(), name='agent-chat-history'),
    path('chat/clear/', AgentChatHistoryClearView.as_view(), name='agent-chat-clear'),
]