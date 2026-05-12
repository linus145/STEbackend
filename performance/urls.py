from django.urls import path, include
from rest_framework.routers import DefaultRouter
from performance.views import KPIViewSet, GoalViewSet, PerformanceReviewViewSet, EmployeeFeedbackViewSet

router = DefaultRouter()
router.register(r'kpis', KPIViewSet)
router.register(r'goals', GoalViewSet)
router.register(r'reviews', PerformanceReviewViewSet)
router.register(r'feedbacks', EmployeeFeedbackViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
