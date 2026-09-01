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

@shared_task
def task_generate_payslip_pdf(payslip_id):
    """
    Celery task to generate a payslip PDF asynchronously.
    """
    try:
        from payroll.models import Payslip
        from payroll.services import PayslipGenerationService
        payslip = Payslip.objects.get(id=payslip_id)
        PayslipGenerationService.async_generate_payslip_pdf(payslip)
        logger.info(f"Successfully generated payslip PDF in background for Payslip {payslip_id}.")
        return {"payslip_id": str(payslip_id), "success": True}
    except Exception as e:
        logger.error(f"Error executing task_generate_payslip_pdf: {e}")
        raise e

@shared_task
def task_email_payslip(payslip_id):
    """
    Celery task to send a payslip email to an employee.
    Generates the up-to-date PDF and attaches it.
    """
    try:
        from payroll.models import Payslip
        from payroll.services import PayslipGenerationService
        from django.core.mail import EmailMultiAlternatives, get_connection
        from django.conf import settings
        from decimal import Decimal

        payslip = Payslip.objects.get(id=payslip_id)
        employee = payslip.employee
        
        # Ensure PDF is available (use already generated PDF if present, otherwise generate on-demand)
        if not payslip.pdf_file:
            PayslipGenerationService.async_generate_payslip_pdf(payslip)
            payslip.refresh_from_db()
            
        recipient_email = employee.email
        if not recipient_email:
            raise ValueError(f"Employee {employee} does not have an email address.")
            
        org_name = employee.organization.name if employee.organization else "B2linq"
        month_name = PayslipGenerationService._month_name(payslip.payroll.month)
        subject = f"Payslip for {month_name} {payslip.payroll.year} - {org_name}"
        
        cur = PayslipGenerationService._get_currency_symbol(payslip)
        record = payslip.payroll_record
        tax_amt = record.tax_amount if record else Decimal('0.00')
        leave_ded = record.leave_deduction if record else Decimal('0.00')
        
        # Split PF & ESI
        pf_calc = Decimal('0.00')
        esi_calc = Decimal('0.00')
        if record and record.pf_amount > 0:
            structure = getattr(employee, 'salary_structure', None)
            if structure:
                pf_calc = (payslip.basic_salary * (structure.pf_percentage / Decimal('100.00'))).quantize(Decimal('0.01'))
                esi_calc = record.pf_amount - pf_calc
                if esi_calc < 0:
                    esi_calc = Decimal('0.00')
                    pf_calc = record.pf_amount
            else:
                pf_calc = (record.pf_amount * Decimal('12.00') / Decimal('13.75')).quantize(Decimal('0.01'))
                esi_calc = record.pf_amount - pf_calc

        other_ded = (record.deductions - (tax_amt + (record.pf_amount if record else Decimal('0.00')) + leave_ded)) if record else Decimal('0.00')
        if other_ded < 0:
            other_ded = Decimal('0.00')
            
        gross_salary = record.gross_salary if record else (payslip.basic_salary + payslip.total_allowances)

        # Calculate HRA and special allowances
        structure = getattr(employee, 'salary_structure', None)
        hra_val = structure.hra if structure else Decimal('0.00')
        
        special_allowances = payslip.total_allowances - hra_val
        if record:
            special_allowances -= (record.overtime_amount + record.reimbursement_amount + record.bonus_amount)
        if special_allowances < 0:
            special_allowances = Decimal('0.00')

        # Build detailed list for markdown
        earnings_list = [f"* **Basic Salary:** {cur}{payslip.basic_salary:,.2f}"]
        if hra_val > 0:
            earnings_list.append(f"* **House Rent Allowance (HRA):** {cur}{hra_val:,.2f}")
        if special_allowances > 0:
            earnings_list.append(f"* **Special/Other Allowances:** {cur}{special_allowances:,.2f}")
        if record and record.overtime_amount > 0:
            earnings_list.append(f"* **Overtime Pay:** {cur}{record.overtime_amount:,.2f}")
        if record and record.reimbursement_amount > 0:
            earnings_list.append(f"* **Reimbursements:** {cur}{record.reimbursement_amount:,.2f}")
        if record and record.bonus_amount > 0:
            earnings_list.append(f"* **Bonus / Incentives:** {cur}{record.bonus_amount:,.2f}")
        
        earnings_md = "\n".join(earnings_list)

        deductions_list = []
        if tax_amt > 0:
            deductions_list.append(f"* **Income Tax (TDS):** {cur}{tax_amt:,.2f}")
        if pf_calc > 0:
            deductions_list.append(f"* **Provident Fund (PF):** {cur}{pf_calc:,.2f}")
        if esi_calc > 0:
            deductions_list.append(f"* **Employee State Insurance (ESI):** {cur}{esi_calc:,.2f}")
        if leave_ded > 0:
            deductions_list.append(f"* **Absence / LOP Deductions:** {cur}{leave_ded:,.2f}")
        if other_ded > 0:
            deductions_list.append(f"* **Other Deductions:** {cur}{other_ded:,.2f}")
        
        deductions_md = "\n".join(deductions_list) if deductions_list else "* *No deductions*"

        # Use our styled HTML builder from template_service
        from payroll.template_service import build_html_email
        email_body = f"""
### PAYSLIP ISSUED

Hello **{employee.first_name} {employee.last_name}**,

Your payslip for the pay period **{month_name} {payslip.payroll.year}** has been successfully generated and published.

### Earnings
{earnings_md}
* **Gross Salary:** {cur}{gross_salary:,.2f}

### Deductions
{deductions_md}
* **Total Deductions:** {cur}{payslip.total_deductions:,.2f}

---
### **Net Payout:** {cur}{payslip.net_salary:,.2f}

Please find your official payslip document attached to this email.

Best Regards,
**HR Operations Team**
        """
        html_content = build_html_email(
            body_text=email_body,
            design_id="corporate",
            recipient_name=f"{employee.first_name} {employee.last_name}",
            template_name=f"Payslip - {month_name} {payslip.payroll.year}",
            org_name=org_name
        )

        notification_host = getattr(settings, 'NOTIFICATION_EMAIL_HOST', None)
        if notification_host:
            connection = get_connection(
                backend=getattr(settings, 'NOTIFICATION_EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend'),
                host=notification_host,
                port=int(getattr(settings, 'NOTIFICATION_EMAIL_PORT', 587)),
                username=getattr(settings, 'NOTIFICATION_EMAIL_HOST_USER', ''),
                password=getattr(settings, 'NOTIFICATION_EMAIL_HOST_PASSWORD', ''),
                use_tls=getattr(settings, 'NOTIFICATION_EMAIL_USE_TLS', True),
            )
            from_email_addr = getattr(settings, 'NOTIFICATION_DEFAULT_FROM_EMAIL', 'lakkavaramlinus@gmail.com')
        else:
            connection = None
            from_email_addr = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@b2linq.com')

        from_email = f"{org_name} <{from_email_addr}>"

        msg = EmailMultiAlternatives(
            subject=subject,
            body=email_body,
            from_email=from_email,
            to=[recipient_email],
            connection=connection
        )
        msg.attach_alternative(html_content, "text/html")
        
        # Attach PDF
        if payslip.pdf_file:
            try:
                # Open the file
                with payslip.pdf_file.open("rb") as f:
                    file_content = f.read()
                filename = f"payslip_{employee.first_name}_{payslip.payroll.month}_{payslip.payroll.year}.pdf"
                msg.attach(filename, file_content, "application/pdf")
            except Exception as e:
                logger.error(f"Failed to attach PDF to email: {e}")

        msg.send(fail_silently=False)
        logger.info(f"Successfully emailed payslip {payslip_id} to {recipient_email}")
        return {"payslip_id": str(payslip_id), "success": True}
    except Exception as e:
        logger.error(f"Error executing task_email_payslip: {e}")
        raise e
