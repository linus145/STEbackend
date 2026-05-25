from django.urls import path
from agentsettings.views import AgentSettingsDetailView, AgentSchedulingDetailView

app_name = "agentsettings"

urlpatterns = [
    path("config/", AgentSettingsDetailView.as_view(), name="agent-config"),
    path("scheduling/", AgentSchedulingDetailView.as_view(), name="agent-scheduling"),
]
