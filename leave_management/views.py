from rest_framework import viewsets, filters, status, decorators
from rest_framework.response import Response
from leave_management.models import LeaveType, LeaveRequest, LeaveBalance
from leave_management.serializers import (
    LeaveTypeSerializer,
    LeaveRequestSerializer,
    LeaveBalanceSerializer,
)
from organization.views import StartupTenantMixin


class LeaveTypeViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer


class LeaveRequestViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = LeaveRequest.objects.select_related("employee", "leave_type").all()
    serializer_class = LeaveRequestSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["employee__first_name", "employee__last_name", "leave_type__name"]

    def get_queryset(self):
        user = self.request.user
        # HR manager/owner sees all leave requests from their organization's employees
        company = getattr(user, "company_profile", None)
        if company:
            from organization.models import Organization
            organization = Organization.objects.filter(company=company).first()
            if organization:
                return self.queryset.filter(employee__organization=organization)
        # Standard employee sees only their own
        employee = getattr(user, "employee_profile", None)
        if employee:
            return self.queryset.filter(employee=employee)
        return self.queryset.none()

    def perform_create(self, serializer):
        employee = getattr(self.request.user, "employee_profile", None)
        if employee:
            serializer.save(employee=employee, startup=employee.startup)
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

        # In a real app, check if the reviewer is an HR or Manager
        leave_request.status = "APPROVED"
        leave_request.approved_by = getattr(request.user, "employee_profile", None)
        leave_request.comment = request.data.get("comment", "")
        leave_request.save()

        # Update balance (simplified)
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


class LeaveBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LeaveBalance.objects.all()
    serializer_class = LeaveBalanceSerializer

    def get_queryset(self):
        user = self.request.user
        # HR manager/owner sees all company balances
        company = getattr(user, "company_profile", None)
        if company:
            from organization.models import Organization
            organization = Organization.objects.filter(company=company).first()
            if organization:
                return self.queryset.filter(employee__organization=organization)
        # Standard employee sees only their own
        employee = getattr(user, "employee_profile", None)
        if employee:
            return self.queryset.filter(employee=employee)

        startup = user.startups.first()
        if startup:
            return self.queryset.filter(employee__startup=startup)

        return self.queryset.none()
