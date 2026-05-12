from django.urls import path, include
from rest_framework.routers import DefaultRouter
from attendance.views import ShiftViewSet, AttendanceViewSet

router = DefaultRouter()
router.register(r'shifts', ShiftViewSet)
router.register(r'records', AttendanceViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
