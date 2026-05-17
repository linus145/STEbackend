from django.urls import path
from .views import AIScreeningHistoryView, AnalyzeResumesView, DeleteScreeningReportView, AIPlanChatView

urlpatterns = [
    path('screening/history/', AIScreeningHistoryView.as_view(), name='ai-screening-history'),
    path('screening/analyze/<uuid:job_id>/', AnalyzeResumesView.as_view(), name='ai-analyze-resumes'),
    path('screening/report/<uuid:report_id>/', DeleteScreeningReportView.as_view(), name='ai-delete-report'),
    path('plan-chat/', AIPlanChatView.as_view(), name='ai-plan-chat'),
]