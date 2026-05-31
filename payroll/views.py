from rest_framework import viewsets, status, decorators
from rest_framework.response import Response
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Q, Count
from django.shortcuts import get_object_or_404
from django.http import HttpResponse

from payroll.models import (
    Allowance,
    Deduction,
    SalaryStructure,
    Payroll,
    PayrollRecord,
    Payslip,
    EmployeeAllowance,
    EmployeeDeduction,
    Reimbursement,
    PayrollAdjustment,
    TaxConfiguration,
    PayrollSetting,
    DocumentTemplate,
)
from payroll.serializers import (
    AllowanceSerializer,
    DeductionSerializer,
    SalaryStructureSerializer,
    PayrollSerializer,
    PayslipSerializer,
    PayrollRecordSerializer,
    ReimbursementSerializer,
    PayrollAdjustmentSerializer,
    TaxConfigurationSerializer,
    DocumentTemplateSerializer,
)
from organization.views import StartupTenantMixin
from employees.models import Employee
from payroll.services import (
    PayrollGenerationService,
    PayrollApprovalService,
    PayrollCalculationService,
    PayslipGenerationService,
)
from payroll.tasks import (
    task_generate_monthly_payroll,
    task_approve_payroll_cycle,
    task_reject_payroll_cycle,
)
from startups.models import Startup
from rest_framework.permissions import IsAuthenticated
from subscription.utils import HasHRToolkitPermission


def get_active_startup(request):
    user = request.user
    if not user or user.is_anonymous:
        return None

    # 1. Try company profile via Organization relation first (as HR tool is linked to organization)
    company = getattr(user, "company_profile", None)
    if company:
        from organization.models import Organization
        org = Organization.objects.filter(company=company).first()
        if org and org.startup:
            return org.startup
        # Fallback to check startup owned by user
        st = Startup.objects.filter(founder=user).first()
        if st:
            return st
        if org:
            return org.startup
        return None

    # 2. Try employee profile
    employee = getattr(user, "employee_profile", None)
    if employee:
        if getattr(employee, "startup", None):
            return employee.startup
        if getattr(employee, "organization", None) and employee.organization.startup:
            return employee.organization.startup

    # 3. Try startups direct relation
    if hasattr(user, 'startups'):
        startup = user.startups.first()
        if startup:
            return startup
            
    return None


class AllowanceViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)
    queryset = Allowance.objects.all()
    serializer_class = AllowanceSerializer
    search_fields = ["name"]


class DeductionViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)
    queryset = Deduction.objects.all()
    serializer_class = DeductionSerializer
    search_fields = ["name"]


class SalaryStructureViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)
    queryset = (
        SalaryStructure.objects.select_related("employee")
        .prefetch_related("employeeallowance_set", "employeededuction_set")
        .all()
    )
    serializer_class = SalaryStructureSerializer

    def get_queryset(self):
        return super().get_queryset().select_related("employee").prefetch_related("employeeallowance_set", "employeededuction_set")

    def destroy(self, request, *args, **kwargs):
        """
        Permanently hard-deletes the salary structure from the database.
        """
        instance = self.get_object()
        instance.hard_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @decorators.action(detail=False, methods=["post"])
    def assign_allowance(self, request):
        structure_id = request.data.get("structure_id")
        allowance_id = request.data.get("allowance_id")
        amount = request.data.get("amount")

        structure = get_object_or_404(SalaryStructure, id=structure_id)
        allowance = get_object_or_404(Allowance, id=allowance_id)

        obj, created = EmployeeAllowance.objects.update_or_create(
            structure=structure, allowance=allowance, defaults={"amount": amount}
        )
        return Response(SalaryStructureSerializer(structure).data)

    @decorators.action(detail=False, methods=["post"])
    def assign_deduction(self, request):
        structure_id = request.data.get("structure_id")
        deduction_id = request.data.get("deduction_id")
        amount = request.data.get("amount")

        structure = get_object_or_404(SalaryStructure, id=structure_id)
        deduction = get_object_or_404(Deduction, id=deduction_id)

        obj, created = EmployeeDeduction.objects.update_or_create(
            structure=structure, deduction=deduction, defaults={"amount": amount}
        )
        return Response(SalaryStructureSerializer(structure).data)


class ReimbursementViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)
    queryset = Reimbursement.objects.select_related("employee").all()
    serializer_class = ReimbursementSerializer
    filterset_fields = ["approval_status", "category"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("employee")
        # Security: Employees only see their own claims. Admins/HR see all startup claims.
        user_email = self.request.user.email
        is_admin_or_hr = (
            self.request.user.groups.filter(
                name__in=["Admin", "HR", "Payroll Manager"]
            ).exists()
            or self.request.user.is_superuser
            or hasattr(self.request.user, 'company_profile')
        )
        if not is_admin_or_hr:
            return qs.filter(employee__email=user_email)
        return qs

    def perform_create(self, serializer):
        # Auto-associate employee based on user context if needed
        startup = get_active_startup(self.request)
        employee = Employee.objects.filter(
            email=self.request.user.email, startup=startup
        ).first()
        if employee:
            serializer.save(employee=employee)
        else:
            serializer.save()

    @decorators.action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        claim = self.get_object()
        claim.approval_status = "APPROVED"
        claim.save()
        return Response(ReimbursementSerializer(claim).data)

    @decorators.action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        claim = self.get_object()
        claim.approval_status = "REJECTED"
        claim.save()
        return Response(ReimbursementSerializer(claim).data)


class PayrollAdjustmentViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)
    queryset = PayrollAdjustment.objects.select_related("employee").all()
    serializer_class = PayrollAdjustmentSerializer

    def get_queryset(self):
        return super().get_queryset().select_related("employee")


class TaxConfigurationViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)
    queryset = TaxConfiguration.objects.all()
    serializer_class = TaxConfigurationSerializer


class PayrollViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)
    queryset = Payroll.objects.prefetch_related("payslips", "records").all()
    serializer_class = PayrollSerializer

    @decorators.action(detail=False, methods=["post"])
    def generate(self, request):
        """
        Action to initiate bulk calculation and draft generation for a specific month and year.
        """
        startup = get_active_startup(self.request)
        if not startup:
            return Response(
                {"error": "No startup profile associated with this account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        month = request.data.get("month")
        year = request.data.get("year")

        if not month or not year:
            return Response(
                {"error": "Please provide both month and year parameters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Get or initialize the draft payroll immediately to return a fast response
            payroll, created = Payroll.objects.get_or_create(
                startup=startup,
                month=int(month),
                year=int(year),
                defaults={"status": "DRAFT"},
            )
            # Dispatch calculations asynchronously to Celery
            task_generate_monthly_payroll.delay(str(startup.id), int(month), int(year))
            return Response(
                {
                    "message": "Payroll calculations dispatched to background workers successfully.",
                    "payroll": PayrollSerializer(payroll).data,
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @decorators.action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """
        Locks the payroll calculations, registers final payouts, marks claims paid, publishes payslips.
        """
        payroll = self.get_object()
        try:
            task_approve_payroll_cycle.delay(str(payroll.id), str(request.user.id))
            return Response(
                {
                    "message": "Payroll final payout authorization and payslip PDF generation dispatched to background workers successfully.",
                    "payroll": PayrollSerializer(payroll).data,
                }
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @decorators.action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """
        Rejects payroll and transitions status back to draft or correction.
        """
        payroll = self.get_object()
        try:
            task_reject_payroll_cycle.delay(str(payroll.id))
            return Response(
                {
                    "message": "Payroll rejection and corrections reversion dispatched to background workers successfully.",
                    "payroll": PayrollSerializer(payroll).data,
                }
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @decorators.action(detail=True, methods=["post"])
    def rerun(self, request, pk=None):
        """
        Action to re-run and recompile a payroll run.
        """
        payroll = self.get_object()
        startup = get_active_startup(self.request)
        if not startup:
            return Response(
                {"error": "No startup profile associated with this account."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Clear existing computed child records safely
        for rec in payroll.records.all():
            rec.hard_delete()
        for ps in payroll.payslips.all():
            ps.hard_delete()
            
        # Reset status to DRAFT
        payroll.status = 'DRAFT'
        payroll.save()
        
        # Dispatch calculation asynchronously
        task_generate_monthly_payroll.delay(str(startup.id), int(payroll.month), int(payroll.year))
        
        return Response(
            {
                "message": "Payroll recalculation and compilation dispatched successfully.",
                "payroll": PayrollSerializer(payroll).data
            },
            status=status.HTTP_200_OK
        )

    def destroy(self, request, *args, **kwargs):
        """
        Permanently hard-deletes the payroll run and all of its associated records.
        """
        instance = self.get_object()
        for rec in instance.records.all():
            rec.hard_delete()
        for ps in instance.payslips.all():
            ps.hard_delete()
        instance.hard_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @decorators.action(detail=False, methods=["get"])
    def analytics(self, request):
        """
        High-fidelity executive payroll dashboard analytics and KPI summaries.
        """
        startup = get_active_startup(self.request)
        if not startup:
            return Response(
                {"error": "No active startup context."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        records = PayrollRecord.objects.filter(employee__startup=startup)

        total_payouts = (
            records.filter(status="APPROVED").aggregate(Sum("net_salary"))[
                "net_salary__sum"
            ]
            or 0.0
        )
        total_tax = (
            records.filter(status="APPROVED").aggregate(Sum("tax_amount"))[
                "tax_amount__sum"
            ]
            or 0.0
        )
        total_pf = (
            records.filter(status="APPROVED").aggregate(Sum("pf_amount"))[
                "pf_amount__sum"
            ]
            or 0.0
        )

        pending_cycles = Payroll.objects.filter(
            startup=startup, status="PROCESSED"
        ).count()
        draft_cycles = Payroll.objects.filter(startup=startup, status="DRAFT").count()
        paid_cycles = Payroll.objects.filter(startup=startup, status="PAID").count()

        # Monthly spending chart data
        trends = []
        cycles = Payroll.objects.filter(startup=startup).order_by("year", "month")[:12]
        for c in cycles:
            net_sum = c.records.aggregate(Sum("net_salary"))["net_salary__sum"] or 0.0
            gross_sum = (
                c.records.aggregate(Sum("gross_salary"))["gross_salary__sum"] or 0.0
            )
            trends.append(
                {
                    "month": f"{c.month}/{c.year}",
                    "net_amount": float(net_sum),
                    "gross_amount": float(gross_sum),
                }
            )

        return Response(
            {
                "total_payroll_amount": float(total_payouts),
                "total_tax_deductions": float(total_tax),
                "total_pf_deductions": float(total_pf),
                "pending_approvals": pending_cycles,
                "draft_cycles": draft_cycles,
                "paid_cycles": paid_cycles,
                "payroll_trends": trends,
            }
        )

    @decorators.action(detail=True, methods=["get"])
    def records_list(self, request, pk=None):
        """
        Returns all employee payroll records generated for a specific payroll cycle.
        """
        payroll = self.get_object()
        records = payroll.records.select_related("employee").all()
        return Response(PayrollRecordSerializer(records, many=True).data)


class PayslipViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)
    queryset = Payslip.objects.select_related("employee", "payroll").all()
    serializer_class = PayslipSerializer

    def get_queryset(self):
        from subscription.utils import check_subscription_feature
        from rest_framework.exceptions import PermissionDenied

        if not self.request.user.is_superuser and not check_subscription_feature(self.request.user, "has_hr_toolkit"):
            raise PermissionDenied("This feature requires an active HRMS/Enterprise subscription plan.")

        startup = get_active_startup(self.request)
        if not startup:
            return Payslip.objects.none()

        base_qs = self.queryset.filter(employee__startup=startup)

        # Security: Employees can only access their own payslips
        is_admin_or_hr = (
            self.request.user.groups.filter(
                name__in=["Admin", "HR", "Payroll Manager"]
            ).exists()
            or self.request.user.is_superuser
            or hasattr(self.request.user, 'company_profile')
        )
        if not is_admin_or_hr:
            return base_qs.filter(
                employee__email=self.request.user.email, is_published=True
            )

        return base_qs

    @decorators.action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """
        Serves the generated payslip file for local download.
        """
        payslip = self.get_object()
        if not payslip.pdf_file:
            # Dynamically ensure one is written
            PayslipGenerationService.async_generate_payslip_pdf(payslip)

        if not payslip.pdf_file:
            return Response(
                {"error": "Payslip document not generated yet."},
                status=status.HTTP_404_NOT_FOUND,
            )

        file_path = payslip.pdf_file.path
        with open(file_path, "rb") as f:
            response = HttpResponse(f.read(), content_type="application/octet-stream")
            response["Content-Disposition"] = (
                f'attachment; filename="payslip_{payslip.employee.first_name}_{payslip.payroll.month}_{payslip.payroll.year}.txt"'
            )
            return response


class PayrollDashboardViewSet(viewsets.ViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)

    def list(self, request):
        startup = get_active_startup(request)
        if not startup:
            return Response(
                {"error": "No active startup context."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        records = PayrollRecord.objects.filter(employee__startup=startup)

        total_payouts = (
            records.filter(status="APPROVED").aggregate(Sum("net_salary"))[
                "net_salary__sum"
            ]
            or 0.0
        )
        total_tax = (
            records.filter(status="APPROVED").aggregate(Sum("tax_amount"))[
                "tax_amount__sum"
            ]
            or 0.0
        )
        total_pf = (
            records.filter(status="APPROVED").aggregate(Sum("pf_amount"))[
                "pf_amount__sum"
            ]
            or 0.0
        )

        pending_cycles = Payroll.objects.filter(
            startup=startup, status="PROCESSED"
        ).count()
        draft_cycles = Payroll.objects.filter(startup=startup, status="DRAFT").count()
        paid_cycles = Payroll.objects.filter(startup=startup, status="PAID").count()

        trends = []
        cycles = Payroll.objects.filter(startup=startup).order_by("year", "month")[:12]
        for c in cycles:
            net_sum = c.records.aggregate(Sum("net_salary"))["net_salary__sum"] or 0.0
            gross_sum = (
                c.records.aggregate(Sum("gross_salary"))["gross_salary__sum"] or 0.0
            )
            trends.append(
                {
                    "month": f"{c.month}/{c.year}",
                    "net_amount": float(net_sum),
                    "gross_amount": float(gross_sum),
                }
            )

        return Response(
            {
                "total_payroll_amount": float(total_payouts),
                "total_tax_deductions": float(total_tax),
                "total_pf_deductions": float(total_pf),
                "pending_approvals": pending_cycles,
                "draft_cycles": draft_cycles,
                "paid_cycles": paid_cycles,
                "payroll_trends": trends,
            }
        )


class PayrollApprovalsViewSet(viewsets.ViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)

    def list(self, request):
        startup = get_active_startup(request)
        if not startup:
            return Response([])
        payrolls = Payroll.objects.filter(startup=startup, status="PROCESSED")
        serializer = PayrollSerializer(payrolls, many=True)
        return Response(serializer.data)


class PayrollReportsViewSet(viewsets.ViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)

    def list(self, request):
        startup = get_active_startup(request)
        if not startup:
            return Response({"departments": [], "active_employees": 0})
        employees = Employee.objects.filter(startup=startup).select_related('department')
        
        dept_map = {}
        for emp in employees:
            dept_name = emp.department.name if emp.department else "General Staff"
            member_name = f"{emp.first_name} {emp.last_name}".strip()
            
            if dept_name not in dept_map:
                dept_map[dept_name] = {
                    "name": dept_name,
                    "members": []
                }
            dept_map[dept_name]["members"].append(member_name)
            
        departments_data = []
        for name, data in dept_map.items():
            departments_data.append({
                "name": name,
                "members": ", ".join(data["members"]),
                "count": len(data["members"])
            })
            
        return Response(
            {"departments": departments_data, "active_employees": employees.count()}
        )


class PayrollSettingsViewSet(viewsets.ViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)

    def list(self, request):
        startup = get_active_startup(request)
        if not startup:
            return Response({"error": "No active startup context."}, status=status.HTTP_400_BAD_REQUEST)
            
        settings, created = PayrollSetting.objects.get_or_create(
            startup=startup,
            defaults={
                "currency": "INR",  # Default to INR (Rupees ₹)
                "automation_enabled": True,
                "pf_percentage": 12.00,
                "esi_percentage": 1.75
            }
        )
        return Response({
            "id": str(settings.id),
            "currency": settings.currency,
            "automation_enabled": settings.automation_enabled,
            "statutory_pf_percentage": float(settings.pf_percentage),
            "statutory_esi_percentage": float(settings.esi_percentage),
            "compliance_status": "COMPLIANT"
        })

    def create(self, request):
        from decimal import Decimal
        startup = get_active_startup(request)
        if not startup:
            return Response({"error": "No active startup context."}, status=status.HTTP_400_BAD_REQUEST)
            
        settings, created = PayrollSetting.objects.get_or_create(
            startup=startup,
            defaults={
                "currency": "INR",
                "automation_enabled": True,
                "pf_percentage": 12.00,
                "esi_percentage": 1.75
            }
        )
        
        currency = request.data.get("currency")
        automation_enabled = request.data.get("automation_enabled")
        pf_percentage = request.data.get("statutory_pf_percentage") or request.data.get("pf_percentage")
        esi_percentage = request.data.get("statutory_esi_percentage") or request.data.get("esi_percentage")
        
        if currency is not None:
            settings.currency = currency
        if automation_enabled is not None:
            settings.automation_enabled = bool(automation_enabled)
        if pf_percentage is not None:
            settings.pf_percentage = Decimal(str(pf_percentage))
        if esi_percentage is not None:
            settings.esi_percentage = Decimal(str(esi_percentage))
            
        settings.save()
        return Response({
            "id": str(settings.id),
            "currency": settings.currency,
            "automation_enabled": settings.automation_enabled,
            "statutory_pf_percentage": float(settings.pf_percentage),
            "statutory_esi_percentage": float(settings.esi_percentage),
            "compliance_status": "COMPLIANT"
        })


class DocumentTemplateViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)
    queryset = DocumentTemplate.objects.all()
    serializer_class = DocumentTemplateSerializer
    search_fields = ["name", "category"]
    filterset_fields = ["category"]

    def perform_create(self, serializer):
        startup = get_active_startup(self.request)
        serializer.save(startup=startup)

    @decorators.action(detail=False, methods=["get"])
    def fetch_payroll_data(self, request):
        employee_id = request.query_params.get("employee_id")
        month = request.query_params.get("month")
        year = request.query_params.get("year")

        if not employee_id:
            return Response({"error": "Employee ID is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not month or not year:
            return Response({"error": "Month and Year are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            month = int(month)
            year = int(year)
        except ValueError:
            return Response({"error": "Invalid Month or Year format."}, status=status.HTTP_400_BAD_REQUEST)

        # Look up the payroll record
        payroll_record = PayrollRecord.objects.filter(
            employee_id=employee_id,
            payroll_cycle__month=month,
            payroll_cycle__year=year
        ).select_related('payroll_cycle').first()

        if not payroll_record:
            return Response({
                "found": False,
                "message": "No payroll record found for the selected month/year."
            })

        # Also get payslip if it exists for extra details (like basic salary and allowances)
        payslip = Payslip.objects.filter(
            employee_id=employee_id,
            payroll__month=month,
            payroll__year=year
        ).first()

        # Let's extract values
        data = {
            "found": True,
            "month": month,
            "year": year,
            "gross_salary": float(payroll_record.gross_salary),
            "net_salary": float(payroll_record.net_salary),
            "tax_amount": float(payroll_record.tax_amount),
            "pf_amount": float(payroll_record.pf_amount),
            "overtime_amount": float(payroll_record.overtime_amount),
            "leave_deduction": float(payroll_record.leave_deduction),
            "reimbursement_amount": float(payroll_record.reimbursement_amount),
            "bonus_amount": float(payroll_record.bonus_amount),
            "total_deductions": float(payroll_record.deductions),
        }

        if payslip:
            data.update({
                "basic_salary": float(payslip.basic_salary),
                "total_allowances": float(payslip.total_allowances),
            })
        else:
            # Fallback to salary structure if payslip object is not created yet
            structure = SalaryStructure.objects.filter(employee_id=employee_id, status='ACTIVE').first()
            if structure:
                data.update({
                    "basic_salary": float(structure.basic_salary),
                    "total_allowances": float(payroll_record.gross_salary - structure.basic_salary) if payroll_record.gross_salary > structure.basic_salary else 0.0,
                })

        return Response(data)

    @decorators.action(detail=False, methods=["post"])
    def send_template(self, request):
        from payroll.tasks import task_send_template_email

        employee_id = request.data.get("employee_id")
        email_body = request.data.get("email_body")
        subject = request.data.get("subject", "Document from HR")
        template_name = request.data.get("template_name", "")
        design_id = request.data.get("design_id", "corporate")

        if not employee_id:
            return Response({"error": "Employee ID is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not email_body:
            return Response({"error": "Email body content is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate employee exists before queuing
        employee = get_object_or_404(Employee, id=employee_id)
        if not employee.email:
            return Response({"error": "Selected employee does not have an email address."}, status=status.HTTP_400_BAD_REQUEST)

        # Dispatch to Celery worker
        task_send_template_email.delay(
            employee_id=str(employee_id),
            email_body=email_body,
            subject=subject or f"Document: {template_name}" or "HR Document",
            template_name=template_name,
            design_id=design_id,
        )

        return Response({
            "status": "success",
            "message": f"Email queued successfully for {employee.first_name} {employee.last_name} ({employee.email}). It will be delivered shortly."
        })
