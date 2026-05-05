from django.urls import path
from .views import AIScreeningHistoryView

urlpatterns = [
    path('screening/history/', AIScreeningHistoryView.as_view(), name='ai-screening-history'),
]