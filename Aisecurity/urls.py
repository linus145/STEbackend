from django.urls import path
from .views import LogViolationView, ProctoringReportView

urlpatterns = [
    path('log-violation/', LogViolationView.as_view(), name='log_violation'),
    path('report/<uuid:session_id>/', ProctoringReportView.as_view(), name='proctoring_report'),
]
