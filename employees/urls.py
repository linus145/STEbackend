from django.urls import path, include
from rest_framework.routers import DefaultRouter
from employees.views import EmployeeViewSet, EmergencyContactViewSet, EmployeeDocumentViewSet, EmployeeLoginView, EmployeeLogoutView

router = DefaultRouter()
router.register(r'employees', EmployeeViewSet)
router.register(r'emergency-contacts', EmergencyContactViewSet)
router.register(r'documents', EmployeeDocumentViewSet)

urlpatterns = [
    path('login/', EmployeeLoginView.as_view(), name='employee-login'),
    path('logout/', EmployeeLogoutView.as_view(), name='employee-logout'),
    path('', include(router.urls)),
]