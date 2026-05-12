from django.urls import path
from Ahrmagent1.views import (
    AgentRunView,
    AgentExecutionDetailView,
    AgentPlanView,
    LLMThinkView,
)

urlpatterns = [
    path('run/', AgentRunView.as_view(), name='agent-run'),
    path('plan/', AgentPlanView.as_view(), name='agent-plan'),
    path('executions/<uuid:pk>/', AgentExecutionDetailView.as_view(), name='agent-execution-detail'),
    # LLM-powered autonomous agent (in-browser, no Playwright needed)
    path('llm/think/', LLMThinkView.as_view(), name='llm-think'),
]