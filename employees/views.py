from rest_framework import viewsets, filters, permissions, status
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from employees.models import Employee, EmployeeProfile, EmergencyContact, EmployeeDocument
from employees.serializers import (
    EmployeeSerializer, EmployeeDetailSerializer, 
    EmployeeProfileSerializer, EmergencyContactSerializer, 
    EmployeeDocumentSerializer
)
from organization.views import StartupTenantMixin

class EmployeeViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Employee.objects.select_related('department', 'designation', 'user', 'profile_details').all()
    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['department', 'designation', 'employment_type', 'status']
    search_fields = ['first_name', 'last_name', 'email', 'employee_id']
    ordering_fields = ['joining_date', 'created_at', 'salary']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return EmployeeDetailSerializer
        return EmployeeSerializer

class EmergencyContactViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = EmergencyContact.objects.all()
    serializer_class = EmergencyContactSerializer
    permission_classes = [permissions.IsAuthenticated]

class EmployeeDocumentViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = EmployeeDocument.objects.all()
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
