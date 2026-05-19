from django.urls import path, include
from rest_framework.routers import DefaultRouter
from organization.views import DepartmentViewSet, DesignationViewSet, OrganizationDetailView

router = DefaultRouter()
router.register(r'departments', DepartmentViewSet)
router.register(r'designations', DesignationViewSet)

urlpatterns = [
    path('detail/', OrganizationDetailView.as_view(), name='organization-detail'),
    path('', include(router.urls)),
]