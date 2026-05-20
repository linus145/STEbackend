from django.urls import path, include
from rest_framework.routers import DefaultRouter
from payroll.views import (
    AllowanceViewSet, DeductionViewSet, SalaryStructureViewSet, 
    PayrollViewSet, PayslipViewSet, ReimbursementViewSet, 
    PayrollAdjustmentViewSet, TaxConfigurationViewSet,
    PayrollDashboardViewSet, PayrollApprovalsViewSet,
    PayrollReportsViewSet, PayrollSettingsViewSet,
    DocumentTemplateViewSet
)

router = DefaultRouter()
router.register(r'allowances', AllowanceViewSet)
router.register(r'deductions', DeductionViewSet)
router.register(r'structures', SalaryStructureViewSet)
router.register(r'salary-structures', SalaryStructureViewSet, basename='salary-structures')
router.register(r'runs', PayrollViewSet)
router.register(r'payslips', PayslipViewSet)
router.register(r'reimbursements', ReimbursementViewSet)
router.register(r'adjustments', PayrollAdjustmentViewSet)
router.register(r'tax-configs', TaxConfigurationViewSet)
router.register(r'tax-configurations', TaxConfigurationViewSet, basename='tax-configurations')
router.register(r'dashboard', PayrollDashboardViewSet, basename='dashboard')
router.register(r'approvals', PayrollApprovalsViewSet, basename='approvals')
router.register(r'reports', PayrollReportsViewSet, basename='reports')
router.register(r'settings', PayrollSettingsViewSet, basename='settings')
router.register(r'templates', DocumentTemplateViewSet, basename='templates')

urlpatterns = [
    path('', include(router.urls)),
]
