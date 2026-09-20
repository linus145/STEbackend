import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from django.db.models import Sum

logger = logging.getLogger(__name__)


def run_payroll_generation_tool(startup, month: int, year: int) -> Dict[str, Any]:
    """
    Tool: Executes the payroll generation pipeline.
    Connects to maincore.payroll services and records draft cycles.
    """
    from payroll.models import Payroll, PayrollRecord
    from payroll.services import PayrollGenerationService

    if not startup:
        # Fallback simulated response when running without an attached startup tenant
        return {
            "is_simulation": True,
            "status": "DRAFT_SIMULATED",
            "message": f"Simulated payroll cycle preview for {month:02d}/{year} (No active startup tenant attached).",
            "employee_count": 0,
            "total_gross": 0.0,
            "total_deductions": 0.0,
            "total_net_payout": 0.0,
            "records": []
        }

    try:
        payroll, count = PayrollGenerationService.generate_monthly_payroll(startup, month, year)
        
        # Aggregate totals for the cycle
        records_qs = PayrollRecord.objects.filter(payroll_cycle=payroll).select_related('employee__user')
        total_gross = records_qs.aggregate(Sum('gross_salary'))['gross_salary__sum'] or Decimal('0.00')
        total_ded = records_qs.aggregate(Sum('deductions'))['deductions__sum'] or Decimal('0.00')
        total_net = records_qs.aggregate(Sum('net_salary'))['net_salary__sum'] or Decimal('0.00')

        records_data = []
        for r in records_qs[:10]:  # sample top records for display
            emp_name = "Employee"
            if r.employee and r.employee.user:
                u = r.employee.user
                full_name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
                emp_name = full_name or getattr(u, 'username', '') or getattr(u, 'email', 'Employee')
            records_data.append({
                "id": str(r.id),
                "employee_name": emp_name,
                "gross_salary": float(r.gross_salary),
                "deductions": float(r.deductions),
                "net_salary": float(r.net_salary),
                "tax_amount": float(r.tax_amount or 0),
            })

        return {
            "is_simulation": False,
            "status": payroll.status,
            "payroll_id": str(payroll.id),
            "employee_count": count,
            "total_gross": float(total_gross),
            "total_deductions": float(total_ded),
            "total_net_payout": float(total_net),
            "records": records_data,
            "message": f"Successfully compiled payroll cycle for {month:02d}/{year} with {count} employees."
        }

    except Exception as e:
        logger.error(f"Error in run_payroll_generation_tool: {e}")
        # Try checking if draft was created anyway
        existing = Payroll.objects.filter(startup=startup, month=month, year=year).first()
        return {
            "is_simulation": False,
            "status": "ERROR",
            "error": str(e),
            "payroll_id": str(existing.id) if existing else None,
            "employee_count": 0,
            "total_gross": 0.0,
            "total_deductions": 0.0,
            "total_net_payout": 0.0,
            "records": []
        }
