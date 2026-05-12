from rest_framework import viewsets, filters, permissions
from django.db.models import Count
from organization.models import Department, Designation
from organization.serializers import DepartmentSerializer, DesignationSerializer

class StartupTenantMixin:
    """
    Mixin to filter querysets by the user's organization or startup.
    Prioritizes Organization (linked to CompanyProfile) but falls back to Startup.
    """
    def get_queryset(self):
        from organization.models import Organization
        user = self.request.user
        
        # Determine the base queryset
        qs = getattr(self, 'queryset', None)
        if qs is None:
            # If no queryset attribute, try to get it from the model
            model = getattr(self, 'model', None)
            if model:
                qs = model.objects.all()
            else:
                return None

        # Ensure we're working with a fresh queryset
        qs = qs.all()

        # 1. Try to filter by Organization (via CompanyProfile)
        company = getattr(user, 'company_profile', None)
        if company:
            organization = Organization.objects.filter(company=company).first()
            if not organization:
                organization = Organization.objects.create(
                    company=company,
                    name=company.company_name
                )
            
            if hasattr(qs.model, 'organization'):
                return qs.filter(organization=organization)
            elif hasattr(qs.model, 'company'):
                return qs.filter(company=company)

        # 2. Fallback to Startup filtering
        startup = user.startups.first()
        if startup:
            if hasattr(qs.model, 'startup'):
                return qs.filter(startup=startup)
            
        # 3. Last resort: return empty if no tenant found
        return qs.none()

class DepartmentViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.annotate(employee_count=Count('employees'))

class DesignationViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Designation.objects.all()
    serializer_class = DesignationSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title']
    ordering_fields = ['title', 'created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.annotate(employee_count=Count('employees'))
