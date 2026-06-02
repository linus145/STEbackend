from django.urls import path
from agentsettings.views import (
    AgentSettingsDetailView,
    AgentSchedulingDetailView,
    AgentSchedulingTriggerView,
    AgentSchedulingLogListView,
    AgentSchedulingLogDetailView
)

app_name = "agentsettings"

urlpatterns = [
    path("config/", AgentSettingsDetailView.as_view(), name="agent-config"),
    path("scheduling/", AgentSchedulingDetailView.as_view(), name="agent-scheduling"),
    path("scheduling/trigger/", AgentSchedulingTriggerView.as_view(), name="agent-scheduling-trigger"),
    path("scheduling/logs/", AgentSchedulingLogListView.as_view(), name="agent-scheduling-logs"),
    path("scheduling/logs/<int:pk>/", AgentSchedulingLogDetailView.as_view(), name="agent-scheduling-log-detail"),
]

