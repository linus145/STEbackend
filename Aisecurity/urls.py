from django.urls import path
from .views import LogViolationView, ProctoringReportView, CodeExecutionView

urlpatterns = [
    path('log-violation/', LogViolationView.as_view(), name='log_violation'),
    path('report/<uuid:session_id>/', ProctoringReportView.as_view(), name='proctoring_report'),
    path('execute-code/', CodeExecutionView.as_view(), name='execute_code'),
]
