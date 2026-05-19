from rest_framework import viewsets, filters, permissions
from django.db.models import Count
from organization.models import Department, Designation, Organization
from organization.serializers import (
    DepartmentSerializer,
    DesignationSerializer,
    OrganizationSerializer,
)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


class StartupTenantMixin:
    """
    Mixin to filter querysets by the user's organization or startup.
    Prioritizes Organization (linked to CompanyProfile) but falls back to Startup.
    Handles Employee profiles transparently to enable correct data isolation.
    """

    def get_queryset(self):
        from organization.models import Organization

        user = self.request.user
        if not user or user.is_anonymous:
            return getattr(self, "queryset", self.model.objects.none() if hasattr(self, "model") else None)

        # Determine the base queryset
        qs = getattr(self, "queryset", None)
        if qs is None:
            # If no queryset attribute, try to get it from the model
            model = getattr(self, "model", None)
            if model:
                qs = model.objects.all()
            else:
                return None

        # Ensure we're working with a fresh queryset
        qs = qs.all()

        # 0. Handle Employee scoping directly
        employee = getattr(user, "employee_profile", None)
        if employee:
            if hasattr(qs.model, "organization") and employee.organization:
                return qs.filter(organization=employee.organization)
            elif hasattr(qs.model, "startup") and employee.startup:
                return qs.filter(startup=employee.startup)

        # 1. Try to filter by Organization (via CompanyProfile) for Founders/HR/Recruiters
        company = getattr(user, "company_profile", None)
        if company:
            organization = Organization.objects.filter(company=company).first()
            if not organization:
                organization = Organization.objects.create(
                    company=company, name=company.company_name
                )

            from django.db.models import Q
            if hasattr(qs.model, "organization"):
                return qs.filter(organization=organization)
            elif hasattr(qs.model, "company"):
                return qs.filter(company=company)
            elif hasattr(qs.model, "employee"):
                return qs.filter(Q(employee__organization=organization) | Q(employee__startup__founder=user))

        # 2. Fallback to Startup filtering
        startup = user.startups.first()
        if startup:
            if hasattr(qs.model, "startup"):
                return qs.filter(startup=startup)

        # 3. Last resort: return empty if no tenant found
        return qs.none()


class DepartmentViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        # Seed predefined departments if none exist for the tenant
        if not qs.exists():
            user = self.request.user
            company = getattr(user, "company_profile", None)
            startup = user.startups.first()
            organization = None
            if company:
                organization, _ = Organization.objects.get_or_create(
                    company=company, defaults={"name": company.company_name}
                )

            predefined = [
                {
                    "name": "Engineering",
                    "description": "Software development, platform stability, and IT infrastructure operations.",
                },
                {
                    "name": "Human Resources",
                    "description": "Talent acquisition, organizational development, employee lifecycle and payroll.",
                },
                {
                    "name": "Product & Design",
                    "description": "Product management, user research, roadmap planning, and visual design operations.",
                },
                {
                    "name": "Quality Assurance",
                    "description": "Software testing, automation testing, CI/CD pipelines quality compliance.",
                },
                {
                    "name": "Sales & Marketing",
                    "description": "Business development, customer outreach, lead generation, and public relations.",
                },
                {
                    "name": "Customer Success",
                    "description": "Customer support, product onboarding, client retention, and relations.",
                },
                {
                    "name": "Finance & Operations",
                    "description": "Bookkeeping, taxes, financial compliance, auditing, and corporate operations.",
                },
            ]

            for item in predefined:
                Department.objects.get_or_create(
                    organization=organization,
                    startup=startup,
                    name=item["name"],
                    defaults={"description": item["description"]},
                )
            # Re-fetch after seeding
            qs = super().get_queryset()

        return qs.annotate(employee_count=Count("employees"))


class DesignationViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Designation.objects.all()
    serializer_class = DesignationSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title"]
    ordering_fields = ["title", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        # Seed predefined designations if none exist for the tenant
        if not qs.exists():
            user = self.request.user
            company = getattr(user, "company_profile", None)
            startup = user.startups.first()
            organization = None
            if company:
                organization, _ = Organization.objects.get_or_create(
                    company=company, defaults={"name": company.company_name}
                )

            predefined = [
                {
                    "title": "Lead Software Engineer",
                    "description": "Lead and direct software engineering projects and team members.",
                },
                {
                    "title": "Senior Software Engineer",
                    "description": "Design, build, and optimize scalable systems and mentoring juniors.",
                },
                {
                    "title": "Software Engineer",
                    "description": "Develop and maintain core software applications and features.",
                },
                {
                    "title": "Junior Software Engineer",
                    "description": "Learn codebase, resolve bugs, and build simple features under guidance.",
                },
                {
                    "title": "Product Manager",
                    "description": "Oversee product lifecycle, roadmap planning, and cross-functional coordination.",
                },
                {
                    "title": "HR Manager",
                    "description": "Manage human resources operations, talent acquisition, and employee engagement.",
                },
                {
                    "title": "Intern",
                    "description": "Learn and work on projects, gaining industrial experience.",
                },
                {
                    "title": "UI/UX Designer",
                    "description": "Design user flows, mockups, prototypes, and ensure exceptional visual design.",
                },
                {
                    "title": "QA Engineer",
                    "description": "Test code quality, author automated test scripts, and log defects.",
                },
                {
                    "title": "Sales Development Representative",
                    "description": "Execute outbound campaigns, identify leads, and close deals.",
                },
            ]

            for item in predefined:
                Designation.objects.get_or_create(
                    organization=organization,
                    startup=startup,
                    title=item["title"],
                    defaults={"description": item["description"]},
                )
            # Re-fetch after seeding
            qs = super().get_queryset()

        return qs.annotate(employee_count=Count("employees"))


class OrganizationDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        company = getattr(user, "company_profile", None)
        if not company:
            return Response(
                {"status": "error", "message": "No company profile found for user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        organization, created = Organization.objects.get_or_create(
            company=company,
            defaults={
                "name": company.company_name,
                "website": company.website,
                "address": company.location,
                "logo_url": company.logo_url,
                "banner_url": company.banner_url,
                "industry": company.industry,
                "company_size": company.company_size,
                "description": company.description,
                "founded_year": company.founded_year,
            },
        )

        # If organization was already created but fields are empty, sync from CompanyProfile
        updated = False
        if not organization.name and company.company_name:
            organization.name = company.company_name
            updated = True
        if not organization.website and company.website:
            organization.website = company.website
            updated = True
        if not organization.address and company.location:
            organization.address = company.location
            updated = True
        if not organization.logo_url and company.logo_url:
            organization.logo_url = company.logo_url
            updated = True
        if not organization.banner_url and company.banner_url:
            organization.banner_url = company.banner_url
            updated = True
        if not organization.industry and company.industry:
            organization.industry = company.industry
            updated = True
        if not organization.company_size and company.company_size:
            organization.company_size = company.company_size
            updated = True
        if not organization.description and company.description:
            organization.description = company.description
            updated = True
        if not organization.founded_year and company.founded_year:
            organization.founded_year = company.founded_year
            updated = True

        if updated:
            organization.save()

        serializer = OrganizationSerializer(organization)
        return Response(serializer.data)

    def patch(self, request):
        user = request.user
        company = getattr(user, "company_profile", None)
        if not company:
            return Response(
                {"status": "error", "message": "No company profile found for user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        organization, _ = Organization.objects.get_or_create(
            company=company,
            defaults={
                "name": company.company_name,
                "website": company.website,
                "address": company.location,
                "logo_url": company.logo_url,
                "banner_url": company.banner_url,
                "industry": company.industry,
                "company_size": company.company_size,
                "description": company.description,
                "founded_year": company.founded_year,
            },
        )

        serializer = OrganizationSerializer(
            organization, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
