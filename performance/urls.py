from django.urls import path, include
from rest_framework.routers import DefaultRouter
from performance.views import (
    KPIViewSet, GoalViewSet, PerformanceReviewViewSet, EmployeeFeedbackViewSet,
    PerformanceCycleViewSet, CompetencyViewSet, CompetencyScoreViewSet
)

router = DefaultRouter()
router.register(r'kpis', KPIViewSet)
router.register(r'goals', GoalViewSet)
router.register(r'reviews', PerformanceReviewViewSet)
router.register(r'feedbacks', EmployeeFeedbackViewSet)
router.register(r'cycles', PerformanceCycleViewSet)
router.register(r'competencies', CompetencyViewSet)
router.register(r'competency-scores', CompetencyScoreViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
