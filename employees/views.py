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

from rest_framework.decorators import action

class EmployeeViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Employee.objects.select_related('department', 'designation', 'user', 'profile_details').all()
    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        'department': ['exact'],
        'designation': ['exact'],
        'employment_type': ['exact'],
        'status': ['exact'],
        'joining_date': ['exact', 'gte', 'lte'],
    }
    search_fields = ['first_name', 'last_name', 'email', 'employee_id']
    ordering_fields = ['joining_date', 'created_at', 'salary']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return EmployeeDetailSerializer
        return EmployeeSerializer

    def perform_create(self, serializer):
        user = self.request.user
        startup = user.startups.first()
        
        # Exact match of StartupTenantMixin logic for visibility
        from organization.models import Organization
        company = getattr(user, 'company_profile', None)
        organization = None
        if company:
            organization = Organization.objects.filter(company=company).first()
            if not organization:
                organization = Organization.objects.create(
                    company=company,
                    name=company.company_name
                )
        
        # Default joining date to today for immediate visibility
        from django.utils import timezone
        joining_date = serializer.validated_data.get('joining_date') or timezone.now().date()
            
        serializer.save(startup=startup, organization=organization, joining_date=joining_date)

    @action(detail=False, methods=['post'], url_path='add-manual')
    def add_manual(self, request):
        data = request.data.copy()
        if 'employee_id' not in data or not data['employee_id']:
            data['employee_id'] = 'TEMP-ID'
            
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

class EmergencyContactViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = EmergencyContact.objects.all()
    serializer_class = EmergencyContactSerializer
    permission_classes = [permissions.IsAuthenticated]

class EmployeeDocumentViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = EmployeeDocument.objects.all()
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
