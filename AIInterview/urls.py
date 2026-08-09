from django.urls import path
from . import views

urlpatterns = [
    path("settings/", views.AIInterviewSettingsView.as_view(), name="ai_interview_settings"),
    path("submit/<uuid:question_id>/", views.AIInterviewSubmitView.as_view(), name="ai_interview_submit"),
    path("chat/", views.AIInterviewChatView.as_view(), name="ai_interview_chat"),
]