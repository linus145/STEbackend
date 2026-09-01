from rest_framework import viewsets, filters, status, decorators
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Q
from maincore.pagination import StandardResultsSetPagination
from leave_management.models import LeaveType, LeaveRequest, LeaveBalance
from leave_management.serializers import (
    LeaveTypeSerializer,
    LeaveRequestSerializer,
    LeaveBalanceSerializer,
)
from organization.views import StartupTenantMixin
from employees.models import Employee


def ensure_default_leave_types(startup=None, organization=None, company=None):
    """
    Ensures that default company leave categories exist for the organization/startup.
    Default Quotas:
      - Annual Leave: 18 days
      - Sick Leave: 10 days
      - Casual Leave: 7 days
      - Maternity/Paternity Leave: 30 days
      - National Holiday / Leave: 0 days
    """
    defaults = [
        {"name": "Annual Leave", "category": "ANNUAL", "max_days_per_year": 18, "is_paid": True, "carry_forward": True, "description": "Standard annual paid vacation entitlement."},
        {"name": "Sick Leave", "category": "SICK", "max_days_per_year": 10, "is_paid": True, "carry_forward": False, "description": "Medical and health-related emergency leave."},
        {"name": "Casual Leave", "category": "CASUAL", "max_days_per_year": 7, "is_paid": True, "carry_forward": False, "description": "Unplanned personal time-off or short casual absences."},
        {"name": "Maternity/Paternity Leave", "category": "OCCASIONAL", "max_days_per_year": 30, "is_paid": True, "carry_forward": False, "description": "Parental leave for childbirth or adoption."},
        {"name": "National Holiday / Leave", "category": "NATIONAL", "max_days_per_year": 0, "is_paid": True, "carry_forward": False, "description": "Gazetted public holidays and optional cultural leaves."},
    ]

    q = Q()
    if startup:
        q |= Q(startup=startup)
    if organization:
        q |= Q(organization=organization)
    if company:
        q |= Q(company=company)

    created_types = []
    for item in defaults:
        existing = LeaveType.objects.filter(q).filter(name__iexact=item["name"]).first() if (startup or organization or company) else LeaveType.objects.filter(name__iexact=item["name"]).first()
        if not existing:
            lt = LeaveType.objects.create(
                startup=startup,
                organization=organization,
                company=company,
                name=item["name"],
                category=item["category"],
                max_days_per_year=item["max_days_per_year"],
                is_paid=item["is_paid"],
                carry_forward=item["carry_forward"],
                description=item["description"],
            )
            created_types.append(lt)
        else:
            created_types.append(existing)
            
    return created_types


def ensure_employee_leave_balances(employee, current_year=None):
    """
    Ensures that an employee has LeaveBalance records for every active company leave type.
    """
    if not employee:
        return
    if not current_year:
        current_year = timezone.now().year
    
    # 1. Ensure company default leave types exist
    ensure_default_leave_types(
        startup=employee.startup,
        organization=employee.organization,
        company=employee.organization.company if employee.organization else None
    )

    # 2. Query all leave types relevant to this employee
    q_filter = Q(startup=employee.startup) if employee.startup else Q()
    if employee.organization:
        q_filter |= Q(organization=employee.organization)
    if employee.organization and employee.organization.company:
        q_filter |= Q(company=employee.organization.company)
    q_filter |= Q(startup=None, organization=None, company=None)

    all_active_types = LeaveType.objects.filter(q_filter).distinct()
    
    for lt in all_active_types:
        LeaveBalance.objects.get_or_create(
            employee=employee,
            leave_type=lt,
            year=current_year,
            defaults={
                'total_days': lt.max_days_per_year or 0.0,
                'used_days': 0.0
            }
        )


class LeaveTypeViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        if user and not user.is_anonymous:
            # Auto-seed defaults if none exist for this context
            company = getattr(user, "company_profile", None)
            employee = getattr(user, "employee_profile", None)
            startup = user.startups.first() if hasattr(user, "startups") else None

            from organization.models import Organization
            org = Organization.objects.filter(company=company).first() if company else (employee.organization if employee else None)
            st = org.startup if (org and org.startup) else (employee.startup if employee else startup)
            comp = company or (org.company if org else None)

            ensure_default_leave_types(startup=st, organization=org, company=comp)

        return super().get_queryset()

    def perform_create(self, serializer):
        user = self.request.user
        
        # 1. Employee profile context
        employee = getattr(user, "employee_profile", None)
        if employee:
            serializer.save(
                startup=employee.startup,
                organization=employee.organization,
                company=employee.organization.company if employee.organization else None
            )
            return

        # 2. Founder/HR company profile context
        company = getattr(user, "company_profile", None)
        if company:
            from organization.models import Organization
            organization = Organization.objects.filter(company=company).first()
            if not organization:
                organization = Organization.objects.create(
                    company=company, name=company.company_name
                )
            
            if not organization.startup:
                from startups.models import Startup
                st = Startup.objects.filter(founder=user, name=company.company_name).first()
                if not st:
                    st = Startup.objects.filter(founder=user).first()
                if not st:
                    st = Startup.objects.first()
                if not st:
                    st = Startup.objects.create(
                        founder=user,
                        name=company.company_name,
                        pitch=company.description or f"Startup profile for {company.company_name}",
                        industry=company.industry or "Technology",
                        stage="Bootstrap",
                        website_url=company.website,
                        logo_url=company.logo_url
                    )
                organization.startup = st
                organization.save()
            startup = organization.startup

            serializer.save(
                startup=startup,
                organization=organization,
                company=company
            )
            return

        # 3. Direct startup fallback
        startup = user.startups.first() if hasattr(user, "startups") else None
        serializer.save(startup=startup)


class LeaveRequestViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = LeaveRequest.objects.select_related("employee", "leave_type").all()
    serializer_class = LeaveRequestSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["employee__first_name", "employee__last_name", "leave_type__name"]

    def get_queryset(self):
        user = self.request.user
        queryset = self.queryset
        
        # HR manager/owner sees all leave requests from their organization's employees
        company = getattr(user, "company_profile", None)
        if company:
            from organization.models import Organization
            organization = Organization.objects.filter(company=company).first()
            if organization:
                queryset = queryset.filter(employee__organization=organization)
            else:
                queryset = self.queryset.none()
        else:
            # Standard employee sees only their own
            employee = getattr(user, "employee_profile", None)
            if employee:
                queryset = queryset.filter(employee=employee)
            else:
                queryset = self.queryset.none()

        # Status filter for pagination support
        status_param = self.request.query_params.get("status")
        if status_param and queryset.exists():
            queryset = queryset.filter(status__iexact=status_param)

        return queryset

    def perform_create(self, serializer):
        employee = getattr(self.request.user, "employee_profile", None)
        if employee:
            serializer.save(
                employee=employee,
                startup=employee.startup,
                organization=employee.organization,
                company=employee.organization.company if employee.organization else None
            )
        else:
            serializer.save()

    @decorators.action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        leave_request = self.get_object()
        if leave_request.status != "PENDING":
            return Response(
                {"error": "Request is already processed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        leave_request.status = "APPROVED"
        leave_request.approved_by = getattr(request.user, "employee_profile", None)
        leave_request.comment = request.data.get("comment", "")
        leave_request.save()

        # Update balance
        balance = LeaveBalance.objects.filter(
            employee=leave_request.employee,
            leave_type=leave_request.leave_type,
            year=leave_request.start_date.year,
        ).first()
        if balance:
            days = (leave_request.end_date - leave_request.start_date).days + 1
            balance.used_days += days
            balance.save()

        return Response(LeaveRequestSerializer(leave_request).data)

    @decorators.action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        leave_request = self.get_object()
        if leave_request.status != "PENDING":
            return Response(
                {"error": "Request is already processed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        leave_request.status = "REJECTED"
        leave_request.comment = request.data.get("comment", "")
        leave_request.save()
        return Response(LeaveRequestSerializer(leave_request).data)


def sync_employee_leave_usage(employee, current_year):
    """
    Synchronizes LeaveBalance.used_days with the actual sum of approved leave request days.
    """
    if not employee:
        return
    approved_requests = LeaveRequest.objects.filter(
        employee=employee,
        status="APPROVED",
        start_date__year=current_year
    )
    
    balances = LeaveBalance.objects.filter(employee=employee, year=current_year)
    for b in balances:
        matching_reqs = approved_requests.filter(
            Q(leave_type=b.leave_type) |
            Q(leave_type__category=b.leave_type.category) |
            Q(leave_type__name__iexact=b.leave_type.name)
        )
        total_used = sum((r.end_date - r.start_date).days + 1 for r in matching_reqs if r.start_date and r.end_date)
        if float(b.used_days) != float(total_used):
            b.used_days = float(total_used)
            b.save(update_fields=['used_days'])


class LeaveBalanceViewSet(viewsets.ModelViewSet):
    queryset = LeaveBalance.objects.select_related("employee", "leave_type").order_by("employee__first_name", "leave_type__name")
    serializer_class = LeaveBalanceSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        "employee__first_name",
        "employee__last_name",
        "employee__email",
        "employee__employee_id",
        "employee__department__name",
        "leave_type__name"
    ]
    ordering_fields = ["employee__first_name", "year", "total_days", "used_days"]

    def get_queryset(self):
        user = self.request.user
        year_param = self.request.query_params.get("year")
        current_year = int(year_param) if (year_param and str(year_param).isdigit()) else timezone.now().year

        qs = self.queryset

        # 1. HR manager/owner sees all company balances
        company = getattr(user, "company_profile", None)
        if company:
            from organization.models import Organization
            organization = Organization.objects.filter(company=company).first()
            if organization:
                qs = qs.filter(employee__organization=organization)
            else:
                return qs.none()

        # 2. Direct startup founder sees all startup employee balances
        elif hasattr(user, "startups") and user.startups.exists():
            startup = user.startups.first()
            qs = qs.filter(employee__startup=startup)

        # 3. Standard employee sees their own balances
        else:
            employee = getattr(user, "employee_profile", None)
            if not employee and user.is_authenticated:
                employee = Employee.objects.filter(email=user.email).first()

            if employee:
                ensure_employee_leave_balances(employee, current_year)
                sync_employee_leave_usage(employee, current_year)
                qs = qs.filter(employee=employee)
            else:
                return qs.none()

        if year_param and str(year_param).isdigit():
            qs = qs.filter(year=int(year_param))

        return qs


class LeaveSettingsViewSet(viewsets.ViewSet):
    """
    Endpoints to view, update, and apply global organization leave policies and quotas.
    """
    def list(self, request):
        user = request.user
        current_year = timezone.now().year

        company = getattr(user, "company_profile", None)
        employee = getattr(user, "employee_profile", None)
        startup = user.startups.first() if hasattr(user, "startups") else None

        from organization.models import Organization
        org = Organization.objects.filter(company=company).first() if company else (employee.organization if employee else None)
        st = org.startup if (org and org.startup) else (employee.startup if employee else startup)
        comp = company or (org.company if org else None)

        ensure_default_leave_types(startup=st, organization=org, company=comp)

        q = Q()
        if st:
            q |= Q(startup=st)
        if org:
            q |= Q(organization=org)
        if comp:
            q |= Q(company=comp)
        q |= Q(startup=None, organization=None, company=None)

        leave_types = LeaveType.objects.filter(q).distinct()
        
        quotas = {}
        for lt in leave_types:
            quotas[lt.category] = {
                "id": str(lt.id),
                "name": lt.name,
                "category": lt.category,
                "max_days_per_year": lt.max_days_per_year or 0,
                "is_paid": lt.is_paid,
                "carry_forward": lt.carry_forward,
                "description": lt.description,
            }

        total_employees = Employee.objects.filter(organization=org).count() if org else (Employee.objects.filter(startup=st).count() if st else 0)

        data = {
            "year": current_year,
            "total_employees": total_employees,
            "quotas": quotas,
            "policies": {
                "allow_negative_balance": False,
                "require_medical_cert_days": 2,
                "advance_notice_days": 3,
                "max_consecutive_days": 14,
                "auto_approval_enabled": False,
            }
        }
        return Response(data)

    @decorators.action(detail=False, methods=["post"])
    def update_settings(self, request):
        user = request.user
        current_year = timezone.now().year
        quotas_payload = request.data.get("quotas", {})
        apply_to_all = request.data.get("apply_to_all_employees", True)

        company = getattr(user, "company_profile", None)
        employee = getattr(user, "employee_profile", None)
        startup = user.startups.first() if hasattr(user, "startups") else None

        from organization.models import Organization
        org = Organization.objects.filter(company=company).first() if company else (employee.organization if employee else None)
        st = org.startup if (org and org.startup) else (employee.startup if employee else startup)
        comp = company or (org.company if org else None)

        ensure_default_leave_types(startup=st, organization=org, company=comp)

        q = Q()
        if st:
            q |= Q(startup=st)
        if org:
            q |= Q(organization=org)
        if comp:
            q |= Q(company=comp)
        q |= Q(startup=None, organization=None, company=None)

        leave_types = LeaveType.objects.filter(q).distinct()

        for lt in leave_types:
            category_key = lt.category
            if category_key in quotas_payload:
                cat_data = quotas_payload[category_key]
                if "max_days_per_year" in cat_data and cat_data["max_days_per_year"] != '':
                    lt.max_days_per_year = int(cat_data["max_days_per_year"])
                if "is_paid" in cat_data:
                    lt.is_paid = bool(cat_data["is_paid"])
                if "carry_forward" in cat_data:
                    lt.carry_forward = bool(cat_data["carry_forward"])
                if "description" in cat_data:
                    lt.description = str(cat_data["description"])
                lt.save()

        # Propagate to all employees if requested
        applied_count = 0
        if apply_to_all:
            employees = Employee.objects.filter(organization=org) if org else (Employee.objects.filter(startup=st) if st else Employee.objects.none())
            for emp in employees:
                ensure_employee_leave_balances(emp, current_year)
                # Update total_days for each category from the quotas_payload
                for category_key, cat_data in quotas_payload.items():
                    if "max_days_per_year" in cat_data and cat_data["max_days_per_year"] != '':
                        new_total = float(cat_data["max_days_per_year"])
                        LeaveBalance.objects.filter(
                            employee=emp,
                            year=current_year,
                            leave_type__category=category_key
                        ).update(total_days=new_total)
                sync_employee_leave_usage(emp, current_year)
                applied_count += 1

        return Response({
            "status": "success",
            "message": f"Leave settings updated and propagated to {applied_count} employees.",
            "applied_employee_count": applied_count
        })
