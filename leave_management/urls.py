from django.urls import path, include
from rest_framework.routers import DefaultRouter
from leave_management.views import (
    LeaveTypeViewSet, 
    LeaveRequestViewSet, 
    LeaveBalanceViewSet,
    LeaveSettingsViewSet
)

router = DefaultRouter()
router.register(r'types', LeaveTypeViewSet)
router.register(r'requests', LeaveRequestViewSet)
router.register(r'balances', LeaveBalanceViewSet)
router.register(r'settings', LeaveSettingsViewSet, basename='leave-settings')

urlpatterns = [
    path('', include(router.urls)),
]