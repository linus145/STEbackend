from rest_framework import viewsets, filters, status, decorators
from rest_framework.response import Response
from django.utils import timezone
from django.db import transaction
from payroll.models import Allowance, Deduction, SalaryStructure, Payroll, Payslip, EmployeeAllowance, EmployeeDeduction
from payroll.serializers import (
    AllowanceSerializer, DeductionSerializer, SalaryStructureSerializer, 
    PayrollSerializer, PayslipSerializer
)
from organization.views import StartupTenantMixin
from employees.models import Employee

class AllowanceViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Allowance.objects.all()
    serializer_class = AllowanceSerializer

class DeductionViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Deduction.objects.all()
    serializer_class = DeductionSerializer

class SalaryStructureViewSet(viewsets.ModelViewSet):
    queryset = SalaryStructure.objects.select_related('employee').prefetch_related('employeeallowance_set', 'employeededuction_set').all()
    serializer_class = SalaryStructureSerializer

    def get_queryset(self):
        startup = self.request.user.startups.first()
        return self.queryset.filter(employee__startup=startup)

class PayrollViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Payroll.objects.prefetch_related('payslips').all()
    serializer_class = PayrollSerializer

    @decorators.action(detail=True, methods=['post'])
    @transaction.atomic
    def process(self, request, pk=None):
        payroll = self.get_object()
        if payroll.status != 'DRAFT':
            return Response({"error": "Payroll already processed"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get all active employees in the startup
        employees = Employee.objects.filter(startup=payroll.startup, status='ACTIVE')
        
        for emp in employees:
            structure = getattr(emp, 'salary_structure', None)
            if not structure:
                continue
            
            total_allowances = sum([a.amount for a in structure.employeeallowance_set.all()])
            total_deductions = sum([d.amount for d in structure.employeededuction_set.all()])
            
            Payslip.objects.update_or_create(
                payroll=payroll,
                employee=emp,
                defaults={
                    'basic_salary': structure.basic_salary,
                    'total_allowances': total_allowances,
                    'total_deductions': total_deductions,
                    'net_salary': structure.basic_salary + total_allowances - total_deductions
                }
            )
            
        payroll.status = 'PROCESSED'
        payroll.processed_at = timezone.now()
        payroll.save()
        
        return Response(PayrollSerializer(payroll).data)

class PayslipViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payslip.objects.select_related('employee', 'payroll').all()
    serializer_class = PayslipSerializer

    def get_queryset(self):
        startup = self.request.user.startups.first()
        return self.queryset.filter(employee__startup=startup)
