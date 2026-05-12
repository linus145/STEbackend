from django.urls import path, include
from rest_framework.routers import DefaultRouter
from payroll.views import AllowanceViewSet, DeductionViewSet, SalaryStructureViewSet, PayrollViewSet, PayslipViewSet

router = DefaultRouter()
router.register(r'allowances', AllowanceViewSet)
router.register(r'deductions', DeductionViewSet)
router.register(r'structures', SalaryStructureViewSet)
router.register(r'runs', PayrollViewSet)
router.register(r'payslips', PayslipViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
