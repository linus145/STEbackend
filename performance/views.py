from rest_framework import viewsets, filters, status, decorators
from rest_framework.response import Response
from performance.models import KPI, Goal, PerformanceReview, EmployeeFeedback, PerformanceCycle, Competency, CompetencyScore
from performance.serializers import (
    KPISerializer, GoalSerializer, 
    PerformanceReviewSerializer, EmployeeFeedbackSerializer,
    PerformanceCycleSerializer, CompetencySerializer, CompetencyScoreSerializer
)
from organization.views import StartupTenantMixin

def resolve_organization_for_user(user):
    organization = None
    if not user or user.is_anonymous:
        return None
    employee = getattr(user, 'employee_profile', None)
    if not employee:
        from employees.models import Employee
        employee = Employee.objects.filter(email=user.email).first()
    
    if employee and employee.organization:
        organization = employee.organization
    
    if not organization:
        company = getattr(user, "company_profile", None)
        if company:
            from organization.models import Organization
            organization = Organization.objects.filter(company=company).first()
                
    if not organization:
        startup = getattr(user, 'startups', None) and user.startups.first()
        if startup:
            from organization.models import Organization
            organization = Organization.objects.filter(startup=startup).first()
            
    return organization

class KPIViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = KPI.objects.all()
    serializer_class = KPISerializer

    def perform_create(self, serializer):
        org = resolve_organization_for_user(self.request.user)
        serializer.save(organization=org)

class GoalViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Goal.objects.select_related('employee', 'kpi').all()
    serializer_class = GoalSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['employee__first_name', 'employee__last_name', 'title']

    def perform_create(self, serializer):
        org = resolve_organization_for_user(self.request.user)
        serializer.save(organization=org)

class PerformanceReviewViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = PerformanceReview.objects.select_related('employee', 'reviewer', 'score_breakdown').all()
    serializer_class = PerformanceReviewSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['employee__first_name', 'employee__last_name']

    def perform_create(self, serializer):
        org = resolve_organization_for_user(self.request.user)
        serializer.save(organization=org)

    @decorators.action(detail=False, methods=['get'])
    def analytics(self, request):
        from performance.services import PerformanceCalculationService
        org = resolve_organization_for_user(self.request.user)
        data = PerformanceCalculationService.get_analytics(org)
        return Response(data)

    @decorators.action(detail=True, methods=['post'])
    def calculate(self, request, pk=None):
        review = self.get_object()
        from performance.services import PerformanceCalculationService
        breakdown = PerformanceCalculationService.calculate_review_score(review)
        return Response({
            'status': 'Calculated', 
            'score': breakdown.final_calculated_score,
            'avg_goal_progress': breakdown.avg_goal_progress,
            'avg_feedback_rating': breakdown.avg_feedback_rating
        })

    @decorators.action(detail=False, methods=['get', 'post'], url_path='generate-insights')
    def generate_insights(self, request):
        org = resolve_organization_for_user(self.request.user)
        if not org:
            return Response({"status": "error", "message": "No organization profile found."}, status=status.HTTP_404_NOT_FOUND)
        from performance.services import PerformanceCalculationService
        insights_data = PerformanceCalculationService.generate_ai_insights(org)
        return Response(insights_data)

class EmployeeFeedbackViewSet(viewsets.ModelViewSet):
    queryset = EmployeeFeedback.objects.select_related('provider', 'review__employee').all()
    serializer_class = EmployeeFeedbackSerializer

    def get_queryset(self):
        org = resolve_organization_for_user(self.request.user)
        return self.queryset.filter(review__organization=org)

class PerformanceCycleViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = PerformanceCycle.objects.all()
    serializer_class = PerformanceCycleSerializer

    def perform_create(self, serializer):
        org = resolve_organization_for_user(self.request.user)
        serializer.save(organization=org)

class CompetencyViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Competency.objects.all()
    serializer_class = CompetencySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Seed predefined competencies if none exist for the tenant
        if not qs.exists():
            org = resolve_organization_for_user(self.request.user)
            if org:
                predefined = [
                    {"name": "Communication", "category": "core", "description": "Expresses ideas clearly, listens effectively, and shares information appropriately."},
                    {"name": "Teamwork", "category": "core", "description": "Collaborates well with others, supports team goals, and builds positive relationships."},
                    {"name": "Problem Solving", "category": "core", "description": "Analyzes issues, identifies root causes, and implements effective solutions."},
                    {"name": "Technical Excellence", "category": "technical", "description": "Demonstrates strong technical expertise and quality in execution of role-specific tasks."},
                    {"name": "Leadership", "category": "leadership", "description": "Guides, motivates, and influences others to achieve goals and growth."}
                ]
                for item in predefined:
                    Competency.objects.get_or_create(
                        organization=org,
                        name=item["name"],
                        defaults={"category": item["category"], "description": item["description"]}
                    )
                qs = super().get_queryset()
        return qs

    def perform_create(self, serializer):
        org = resolve_organization_for_user(self.request.user)
        serializer.save(organization=org)

class CompetencyScoreViewSet(viewsets.ModelViewSet):
    queryset = CompetencyScore.objects.select_related('competency', 'review').all()
    serializer_class = CompetencyScoreSerializer

    def get_queryset(self):
        org = resolve_organization_for_user(self.request.user)
        return self.queryset.filter(review__organization=org)
