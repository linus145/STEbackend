from rest_framework import viewsets, filters, status, decorators
from rest_framework.response import Response
from performance.models import KPI, Goal, PerformanceReview, EmployeeFeedback
from performance.serializers import (
    KPISerializer, GoalSerializer, 
    PerformanceReviewSerializer, EmployeeFeedbackSerializer
)
from organization.views import StartupTenantMixin

class KPIViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = KPI.objects.all()
    serializer_class = KPISerializer

class GoalViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Goal.objects.select_related('employee', 'kpi').all()
    serializer_class = GoalSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['employee__first_name', 'employee__last_name', 'title']

class PerformanceReviewViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = PerformanceReview.objects.select_related('employee', 'reviewer').all()
    serializer_class = PerformanceReviewSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['employee__first_name', 'employee__last_name']

class EmployeeFeedbackViewSet(viewsets.ModelViewSet):
    queryset = EmployeeFeedback.objects.select_related('provider', 'review__employee').all()
    serializer_class = EmployeeFeedbackSerializer

    def get_queryset(self):
        startup = self.request.user.startups.first()
        return self.queryset.filter(review__startup=startup)
