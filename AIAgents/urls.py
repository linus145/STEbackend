from django.urls import path
from AIagents.views import AgentTaskExecuteView

urlpatterns = [
    path('execute/', AgentTaskExecuteView.as_view(), name='agent_execute'),
]

# base url -/api/AIAgents