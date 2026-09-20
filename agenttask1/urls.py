from django.urls import path
from agenttask1.views import ExecuteAgentTaskView, ParseIntentView, ListAvailableToolsView

app_name = "agenttask1"

urlpatterns = [
    path("execute/", ExecuteAgentTaskView.as_view(), name="execute"),
    path("parse-intent/", ParseIntentView.as_view(), name="parse_intent"),
    path("tools/", ListAvailableToolsView.as_view(), name="tools"),
]