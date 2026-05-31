import logging
from celery import shared_task
from startups.models import Startup
from useraccounts.models import CustomUser
from payroll.models import Payroll
from payroll.services import PayrollGenerationService, PayrollApprovalService

logger = logging.getLogger("payroll.tasks")

@shared_task
def task_generate_monthly_payroll(startup_id, month, year):
    """
    Celery task to compile attendance inputs and generate draft payroll cycle records asynchronously.
    """
    try:
        startup = Startup.objects.get(id=startup_id)
        payroll, count = PayrollGenerationService.generate_monthly_payroll(startup, int(month), int(year))
        logger.info(f"Successfully generated payroll cycle in background: {month}/{year} for {count} employees.")
        return {"payroll_id": str(payroll.id), "employee_count": count}
    except Exception as e:
        logger.error(f"Error executing task_generate_monthly_payroll: {e}")
        try:
            from payroll.models import Payroll
            payroll = Payroll.objects.filter(startup_id=startup_id, month=int(month), year=int(year)).first()
            if payroll:
                payroll.status = 'FAILED'
                payroll.save(update_fields=['status'])
        except Exception as ex:
            logger.error(f"Failed to transition payroll to FAILED status: {ex}")
        raise e

@shared_task
def task_approve_payroll_cycle(payroll_id, approver_user_id):
    """
    Celery task to lock salary values, finalize reimbursements, publish payslips, and dispatch PDFs.
    """
    try:
        success = PayrollApprovalService.approve_payroll_cycle(payroll_id, approver_user_id)
        logger.info(f"Successfully approved payroll cycle {payroll_id} in background by User {approver_user_id}.")
        return {"success": success}
    except Exception as e:
        logger.error(f"Error executing task_approve_payroll_cycle: {e}")
        try:
            from payroll.models import Payroll
            payroll = Payroll.objects.get(id=payroll_id)
            payroll.status = 'FAILED'
            payroll.save(update_fields=['status'])
        except Exception as ex:
            logger.error(f"Failed to transition payroll status to FAILED: {ex}")
        raise e

@shared_task
def task_reject_payroll_cycle(payroll_id):
    """
    Celery task to reject processed calculations and revert cycle back to corrections draft.
    """
    try:
        success = PayrollApprovalService.reject_payroll_cycle(payroll_id)
        logger.info(f"Successfully rejected payroll cycle {payroll_id} in background.")
        return {"success": success}
    except Exception as e:
        logger.error(f"Error executing task_reject_payroll_cycle: {e}")
        try:
            from payroll.models import Payroll
            payroll = Payroll.objects.get(id=payroll_id)
            payroll.status = 'FAILED'
            payroll.save(update_fields=['status'])
        except Exception as ex:
            logger.error(f"Failed to transition payroll status to FAILED: {ex}")
        raise e

@shared_task
def task_send_template_email(employee_id, email_body, subject, template_name="", design_id="corporate"):
    """
    Celery task to build styled HTML email and send it to an employee asynchronously.
    """
    try:
        from payroll.template_service import send_template_email
        result = send_template_email(
            employee_id=employee_id,
            email_body=email_body,
            subject=subject,
            template_name=template_name,
            design_id=design_id,
        )
        logger.info(f"Successfully sent template email in background: {result.get('message', '')}")
        return result
    except Exception as e:
        logger.error(f"Error executing task_send_template_email: {e}")
        raise e
