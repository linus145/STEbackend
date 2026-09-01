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
    task_generate_payslip_pdf,
    task_email_payslip,
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


def _get_employee_q_for_startup(startup, prefix=''):
    """
    Returns a Q filter that matches employees belonging to the given startup,
    either via the direct startup FK or via the organization linked to the startup.
    Use prefix='employee__' when filtering from a related model (Payslip, PayrollRecord).
    """
    from organization.models import Organization
    org = Organization.objects.filter(startup=startup).first()
    if org:
        return Q(**{f'{prefix}startup': startup}) | Q(**{f'{prefix}organization': org})
    return Q(**{f'{prefix}startup': startup})


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


from decimal import Decimal
from maincore.pagination import StandardResultsSetPagination


class SalaryStructureViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)
    pagination_class = StandardResultsSetPagination
    queryset = (
        SalaryStructure.objects.select_related("employee")
        .prefetch_related("employeeallowance_set", "employeededuction_set")
        .all()
    )
    serializer_class = SalaryStructureSerializer

    def get_queryset(self):
        return super().get_queryset().select_related("employee").prefetch_related("employeeallowance_set", "employeededuction_set").order_by("employee__first_name", "employee__last_name")

    def create(self, request, *args, **kwargs):
        from payroll.serializers import resolve_employee_id_in_data
        data = resolve_employee_id_in_data(request.data)
        emp_id = data.get("employee")
        if emp_id:
            existing = SalaryStructure.objects.filter(employee_id=emp_id).first()
            if existing:
                serializer = self.get_serializer(existing, data=data, partial=True)
                serializer.is_valid(raise_exception=True)
                self.perform_update(serializer)
                return Response(serializer.data, status=status.HTTP_200_OK)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """
        Permanently hard-deletes the salary structure from the database.
        """
        instance = self.get_object()
        instance.hard_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @decorators.action(detail=False, methods=["post"], url_path="bulk-import")
    def bulk_import(self, request):
        """
        POST /api/payroll/structures/bulk-import/
        Imports or updates a batch of salary structures for employees.
        Matches employee by employee_id, email, or id.
        """
        from employees.models import Employee
        structures_data = request.data.get("structures", [])
        if not isinstance(structures_data, list) or len(structures_data) == 0:
            return Response({"error": "No salary structure records provided."}, status=status.HTTP_400_BAD_REQUEST)

        tenant_employees = Employee.objects.filter(self.get_tenant_filter(), is_deleted=False)
        emp_by_id = {str(e.employee_id).strip().lower(): e for e in tenant_employees if e.employee_id}
        emp_by_email = {str(e.email).strip().lower(): e for e in tenant_employees if e.email}
        emp_by_uuid = {str(e.id): e for e in tenant_employees}

        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []

        for idx, row in enumerate(structures_data):
            row_num = idx + 1
            try:
                emp_id_val = str(row.get("employee_id") or "").strip().lower()
                emp_email_val = str(row.get("email") or row.get("work_email") or "").strip().lower()
                emp_direct_val = str(row.get("employee") or "").strip().lower()

                employee_obj = (
                    emp_by_id.get(emp_id_val)
                    or emp_by_email.get(emp_email_val)
                    or emp_by_id.get(emp_direct_val)
                    or emp_by_email.get(emp_direct_val)
                    or emp_by_uuid.get(emp_direct_val)
                    or emp_by_uuid.get(emp_id_val)
                )

                if not employee_obj:
                    identifier = emp_id_val or emp_email_val or emp_direct_val or f"Row {row_num}"
                    errors.append(f"Row {row_num}: Employee '{identifier}' not found in active directory.")
                    skipped_count += 1
                    continue

                try:
                    basic_salary = Decimal(str(row.get("basic_salary") or row.get("basic") or 0).replace(",", "").strip())
                except Exception:
                    basic_salary = Decimal("0.00")

                try:
                    hra = Decimal(str(row.get("hra") or 0).replace(",", "").strip())
                except Exception:
                    hra = Decimal("0.00")

                try:
                    overtime_rate = Decimal(str(row.get("overtime_rate") or row.get("ot_rate") or 0).replace(",", "").strip())
                except Exception:
                    overtime_rate = Decimal("0.00")

                try:
                    tax_percentage = Decimal(str(row.get("tax_percentage") or row.get("tax") or 10).replace(",", "").strip())
                except Exception:
                    tax_percentage = Decimal("10.00")

                try:
                    pf_percentage = Decimal(str(row.get("pf_percentage") or row.get("pf") or 12).replace(",", "").strip())
                except Exception:
                    pf_percentage = Decimal("12.00")

                try:
                    esi_percentage = Decimal(str(row.get("esi_percentage") or row.get("esi") or 1.75).replace(",", "").strip())
                except Exception:
                    esi_percentage = Decimal("1.75")

                status_val = str(row.get("status") or "ACTIVE").strip().upper()
                if status_val not in ["ACTIVE", "INACTIVE"]:
                    status_val = "ACTIVE"

                obj, created = SalaryStructure.objects.update_or_create(
                    employee=employee_obj,
                    defaults={
                        "basic_salary": basic_salary,
                        "hra": hra,
                        "overtime_rate": overtime_rate,
                        "tax_percentage": tax_percentage,
                        "pf_percentage": pf_percentage,
                        "esi_percentage": esi_percentage,
                        "status": status_val,
                        "is_deleted": False,
                        "deleted_at": None,
                    }
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as row_err:
                errors.append(f"Row {row_num}: {str(row_err)}")
                skipped_count += 1

        return Response(
            {
                "status": "SUCCESS",
                "created_count": created_count,
                "updated_count": updated_count,
                "total_processed": created_count + updated_count,
                "skipped_count": skipped_count,
                "errors": errors,
                "message": f"Successfully processed {created_count + updated_count} salary structures.",
            },
            status=status.HTTP_200_OK,
        )

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
        if payroll.status != 'PROCESSED':
            return Response({"error": f"Only processed payrolls can be approved. Current status is {payroll.status}"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Fetch startup's PayrollSetting
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

        # 1. Finance Manager Stage Check
        if settings.finance_approval_required and not payroll.finance_approved:
            # Current user must be the designated finance manager
            if settings.finance_manager and request.user.id != settings.finance_manager.id:
                return Response(
                    {"error": "Only the designated Finance Manager can approve this stage."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            payroll.finance_approved = True
            payroll.finance_approved_by = request.user
            payroll.finance_approved_at = timezone.now()
            
            # If Director is also required, we save but DO NOT transition to APPROVED yet
            if settings.director_approval_required and not payroll.director_approved:
                payroll.save()
                return Response({
                    "message": "L1 (Finance Manager) approval recorded successfully. Awaiting L2 (Director) approval.",
                    "payroll": PayrollSerializer(payroll).data,
                })
            
            # If Director is not required, L1 approval is final
            payroll.status = 'APPROVED'
            payroll.save()
            try:
                task_approve_payroll_cycle.delay(str(payroll.id), str(request.user.id))
                return Response({
                    "message": "Payroll approved and finalized successfully.",
                    "payroll": PayrollSerializer(payroll).data,
                })
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Director Stage Check (Runs if L1 is done or not required)
        if settings.director_approval_required and not payroll.director_approved:
            # Current user must be the designated director
            if settings.director and request.user.id != settings.director.id:
                return Response(
                    {"error": "Only the designated Director can approve this stage."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            payroll.director_approved = True
            payroll.director_approved_by = request.user
            payroll.director_approved_at = timezone.now()
            payroll.status = 'APPROVED'
            payroll.save()
            try:
                task_approve_payroll_cycle.delay(str(payroll.id), str(request.user.id))
                return Response({
                    "message": "Payroll final payout authorization and payslip PDF generation dispatched successfully.",
                    "payroll": PayrollSerializer(payroll).data,
                })
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Direct/Standard Stage (No hierarchy required)
        payroll.status = 'APPROVED'
        payroll.save()
        try:
            task_approve_payroll_cycle.delay(str(payroll.id), str(request.user.id))
            return Response(
                {
                    "message": "Payroll approved and finalized successfully.",
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
        if payroll.status != 'PROCESSED':
            return Response({"error": f"Only processed payrolls can be rejected. Current status is {payroll.status}"}, status=status.HTTP_400_BAD_REQUEST)
            
        # Transition status synchronously to prevent UI race conditions
        payroll.status = 'REJECTED'
        payroll.finance_approved = False
        payroll.finance_approved_by = None
        payroll.finance_approved_at = None
        payroll.director_approved = False
        payroll.director_approved_by = None
        payroll.director_approved_at = None
        payroll.save()

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
        
        # Recalculate payroll immediately
        try:
            payroll, count = PayrollGenerationService.generate_monthly_payroll(startup, int(payroll.month), int(payroll.year))
        except Exception as e:
            task_generate_monthly_payroll.delay(str(startup.id), int(payroll.month), int(payroll.year))
        
        payroll.refresh_from_db()
        return Response(
            {
                "message": "Payroll recalculation completed successfully.",
                "payroll": PayrollSerializer(payroll).data
            },
            status=status.HTTP_200_OK
        )

    @decorators.action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        """
        Returns real-time payslip generation progress for this payroll run.
        """
        payroll = self.get_object()
        total_records = payroll.records.count()
        total_payslips = payroll.payslips.count()
        generated_payslips = payroll.payslips.exclude(pdf_file='').exclude(pdf_file__isnull=True).count()
        target_total = total_payslips if total_payslips > 0 else (total_records or 1)

        return Response({
            "payroll_id": str(payroll.id),
            "status": payroll.status,
            "total_count": target_total,
            "generated_count": generated_payslips,
            "is_complete": payroll.status == 'APPROVED' and (generated_payslips >= target_total if target_total > 0 else True)
        })

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

        emp_q = _get_employee_q_for_startup(startup, prefix='employee__')
        records = PayrollRecord.objects.filter(emp_q).filter(employee__status='ACTIVE')

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


class PayslipViewSet(viewsets.ModelViewSet):
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

        emp_q = _get_employee_q_for_startup(startup, prefix='employee__')
        base_qs = self.queryset.filter(emp_q)

        # Security: Employees can only access their own payslips
        is_admin_or_hr = (
            self.request.user.groups.filter(
                name__in=["Admin", "HR", "Payroll Manager"]
            ).exists()
            or self.request.user.is_superuser
            or hasattr(self.request.user, 'company_profile')
        )
        if not is_admin_or_hr:
            base_qs = base_qs.filter(
                employee__email=self.request.user.email, is_published=True
            )

        # Delegate to the canonical searchfilters service for month/year/search filtering
        from searchfilters.services import SearchService
        filters = {
            "month": self.request.query_params.get("month"),
            "year": self.request.query_params.get("year"),
            "search": self.request.query_params.get("search"),
            "ordering": self.request.query_params.get("ordering"),
        }
        return SearchService.filter_payslips(base_qs, filters)

    @decorators.action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """
        Serves the generated payslip file for local download.
        Supports lookup by Payslip ID or fallback to PayrollRecord ID.
        """
        queryset = self.filter_queryset(self.get_queryset())
        payslip = queryset.filter(pk=pk).first()
        if not payslip:
            # Fallback: the UI might pass the PayrollRecord ID instead of the Payslip ID
            payslip = queryset.filter(payroll_record_id=pk).first()

        if not payslip:
            from django.http import Http404
            raise Http404("No Payslip matches the given query.")

        # Generate payslip PDF on-demand only if not already generated
        if not payslip.pdf_file:
            try:
                PayslipGenerationService.async_generate_payslip_pdf(payslip)
                payslip.refresh_from_db()
            except Exception as e:
                import logging
                logging.getLogger("payroll.views").warning(
                    f"On-demand PDF generation failed: {e}."
                )

        if not payslip.pdf_file:
            return Response(
                {"error": "Payslip document not generated yet."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            with payslip.pdf_file.open("rb") as f:
                file_content = f.read()
        except Exception:
            try:
                file_url = payslip.pdf_file.url if hasattr(payslip.pdf_file, "url") else str(payslip.pdf_file)
                if file_url.startswith("http://") or file_url.startswith("https://"):
                    import httpx
                    resp = httpx.get(file_url, timeout=15.0)
                    if resp.status_code == 200:
                        file_content = resp.content
                    else:
                        raise Exception(f"HTTP {resp.status_code} fetching remote file")
                else:
                    with open(payslip.pdf_file.path, "rb") as f:
                        file_content = f.read()
            except Exception as e:
                return Response(
                    {"error": f"Failed to read payslip file: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        first_name = getattr(payslip.employee, "first_name", "employee") or "employee"
        file_basename = f"payslip_{first_name}_{payslip.payroll.month}_{payslip.payroll.year}"
        file_str = str(payslip.pdf_file.name or payslip.pdf_file)
        if file_str.lower().endswith(".pdf") or ".pdf" in file_str.lower():
            content_type = "application/pdf"
            filename = f"{file_basename}.pdf"
        else:
            content_type = "application/octet-stream"
            filename = f"{file_basename}.txt"

        response = HttpResponse(file_content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @decorators.action(detail=True, methods=["post"])
    def send_email(self, request, pk=None):
        """
        Sends the payslip via email to the employee.
        """
        queryset = self.filter_queryset(self.get_queryset())
        payslip = queryset.filter(pk=pk).first()
        if not payslip:
            payslip = queryset.filter(payroll_record_id=pk).first()

        if not payslip:
            return Response(
                {"error": "No Payslip matches the given query."},
                status=status.HTTP_404_NOT_FOUND,
            )

        task_email_payslip.delay(str(payslip.id))
        return Response({"message": "Payslip email has been queued for sending."})

    @decorators.action(detail=False, methods=["GET", "POST"])
    def bulk_send_emails(self, request):
        """
        Bulk sends emails for all payslips matching the query filters (e.g. month & year).
        """
        queryset = self.filter_queryset(self.get_queryset())
        # Filter to only send for published payslips
        queryset = queryset.filter(is_published=True)
        count = 0
        for payslip in queryset:
            task_email_payslip.delay(str(payslip.id))
            count += 1
        return Response({"message": f"Bulk sending process started for {count} payslips."})

    def destroy(self, request, *args, **kwargs):
        """
        Permanently hard-deletes a single payslip and its associated payroll record.
        """
        instance = self.get_object()
        record = instance.payroll_record
        instance.hard_delete()
        if record:
            record.hard_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PayrollDashboardViewSet(viewsets.ViewSet):
    permission_classes = (IsAuthenticated, HasHRToolkitPermission)

    def list(self, request):
        startup = get_active_startup(request)
        if not startup:
            return Response(
                {"error": "No active startup context."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        emp_q = _get_employee_q_for_startup(startup, prefix='employee__')
        records = PayrollRecord.objects.filter(emp_q).filter(employee__status='ACTIVE')

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
        emp_q = _get_employee_q_for_startup(startup)
        employees = Employee.objects.filter(emp_q).select_related('department')
        
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
            "tax_percentage": float(settings.tax_percentage),
            "statutory_tax_percentage": float(settings.tax_percentage),
            "enable_tax_deductions": settings.enable_tax_deductions,
            "enable_statutory_deductions": settings.enable_statutory_deductions,
            "enable_leave_deductions": settings.enable_leave_deductions,
            "compliance_status": "COMPLIANT",
            "finance_approval_required": settings.finance_approval_required,
            "finance_manager": str(settings.finance_manager.id) if settings.finance_manager else None,
            "finance_manager_name": f"{settings.finance_manager.employee_profile.first_name} {settings.finance_manager.employee_profile.last_name}" if settings.finance_manager and getattr(settings.finance_manager, 'employee_profile', None) else (settings.finance_manager.username if settings.finance_manager else None),
            "director_approval_required": settings.director_approval_required,
            "director": str(settings.director.id) if settings.director else None,
            "director_name": f"{settings.director.employee_profile.first_name} {settings.director.employee_profile.last_name}" if settings.director and getattr(settings.director, 'employee_profile', None) else (settings.director.username if settings.director else None),
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
        tax_percentage = request.data.get("statutory_tax_percentage") or request.data.get("tax_percentage")
        enable_tax_deductions = request.data.get("enable_tax_deductions")
        enable_statutory_deductions = request.data.get("enable_statutory_deductions")
        enable_leave_deductions = request.data.get("enable_leave_deductions")
        
        finance_approval_required = request.data.get("finance_approval_required")
        finance_manager_id = request.data.get("finance_manager")
        director_approval_required = request.data.get("director_approval_required")
        director_id = request.data.get("director")
        
        def parse_bool(val, default=True):
            if val is None:
                return default
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.strip().lower() not in ['false', '0', 'off', 'no', 'null', 'undefined', '']
            if isinstance(val, (int, float)):
                return val != 0
            return bool(val)

        if currency is not None:
            settings.currency = currency
        if automation_enabled is not None:
            settings.automation_enabled = parse_bool(automation_enabled, True)
        if pf_percentage is not None:
            settings.pf_percentage = Decimal(str(pf_percentage))
            SalaryStructure.objects.filter(
                Q(employee__startup=startup) | Q(employee__organization__startup=startup)
            ).update(pf_percentage=settings.pf_percentage)
        if esi_percentage is not None:
            settings.esi_percentage = Decimal(str(esi_percentage))
            SalaryStructure.objects.filter(
                Q(employee__startup=startup) | Q(employee__organization__startup=startup)
            ).update(esi_percentage=settings.esi_percentage)
        if tax_percentage is not None:
            settings.tax_percentage = Decimal(str(tax_percentage))
            SalaryStructure.objects.filter(
                Q(employee__startup=startup) | Q(employee__organization__startup=startup)
            ).update(tax_percentage=settings.tax_percentage)
        if enable_tax_deductions is not None:
            settings.enable_tax_deductions = parse_bool(enable_tax_deductions, True)
        if enable_statutory_deductions is not None:
            settings.enable_statutory_deductions = parse_bool(enable_statutory_deductions, True)
        if enable_leave_deductions is not None:
            settings.enable_leave_deductions = parse_bool(enable_leave_deductions, True)
            
        if finance_approval_required is not None:
            settings.finance_approval_required = parse_bool(finance_approval_required, False)
        if finance_manager_id is not None:
            if finance_manager_id == "":
                settings.finance_manager = None
            else:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                settings.finance_manager = User.objects.filter(id=finance_manager_id).first()
        elif settings.finance_approval_required is False:
            settings.finance_manager = None

        if director_approval_required is not None:
            settings.director_approval_required = parse_bool(director_approval_required, False)
        if director_id is not None:
            if director_id == "":
                settings.director = None
            else:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                settings.director = User.objects.filter(id=director_id).first()
        elif settings.director_approval_required is False:
            settings.director = None
            
        settings.save()

        # Auto-recalculate active draft payroll runs for this startup to immediately reflect new settings
        for p in Payroll.objects.filter(startup=startup, status='DRAFT'):
            try:
                PayrollGenerationService.generate_monthly_payroll(startup, int(p.month), int(p.year))
            except Exception:
                pass

        return Response({
            "id": str(settings.id),
            "currency": settings.currency,
            "automation_enabled": settings.automation_enabled,
            "statutory_pf_percentage": float(settings.pf_percentage),
            "statutory_esi_percentage": float(settings.esi_percentage),
            "tax_percentage": float(settings.tax_percentage),
            "statutory_tax_percentage": float(settings.tax_percentage),
            "enable_tax_deductions": settings.enable_tax_deductions,
            "enable_statutory_deductions": settings.enable_statutory_deductions,
            "enable_leave_deductions": settings.enable_leave_deductions,
            "compliance_status": "COMPLIANT",
            "finance_approval_required": settings.finance_approval_required,
            "finance_manager": str(settings.finance_manager.id) if settings.finance_manager else None,
            "finance_manager_name": f"{settings.finance_manager.employee_profile.first_name} {settings.finance_manager.employee_profile.last_name}" if settings.finance_manager and getattr(settings.finance_manager, 'employee_profile', None) else (settings.finance_manager.username if settings.finance_manager else None),
            "director_approval_required": settings.director_approval_required,
            "director": str(settings.director.id) if settings.director else None,
            "director_name": f"{settings.director.employee_profile.first_name} {settings.director.employee_profile.last_name}" if settings.director and getattr(settings.director, 'employee_profile', None) else (settings.director.username if settings.director else None),
        })

    def update(self, request, pk=None):
        return self.create(request)

    def partial_update(self, request, pk=None):
        return self.create(request)


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
