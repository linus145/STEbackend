import datetime
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum
from payroll.models import (
    Payroll, PayrollRecord, Payslip, SalaryStructure,
    Reimbursement, PayrollAdjustment, TaxConfiguration
)
from employees.models import Employee
from attendance.models import Attendance
from leave_management.models import LeaveRequest

class TaxCalculationService:
    """
    Service to calculate income tax dynamically based on tax configurations/slabs or salary structure fallback.
    """
    @staticmethod
    def calculate_tax(employee, taxable_income):
        startup = employee.startup
        slabs = TaxConfiguration.objects.filter(startup=startup).order_by('min_amount')
        
        if not slabs.exists():
            # Fallback to structure tax_percentage if no slabs are configured
            structure = getattr(employee, 'salary_structure', None)
            if structure and structure.tax_percentage > 0:
                return (taxable_income * (structure.tax_percentage / Decimal('100.00'))).quantize(Decimal('0.01'))
            return Decimal('0.00')

        tax = Decimal('0.00')
        for slab in slabs:
            min_amt = slab.min_amount
            max_amt = slab.max_amount if slab.max_amount else Decimal('999999999.99')
            pct = slab.percentage / Decimal('100.00')

            if taxable_income > min_amt:
                taxable_in_slab = min(taxable_income - min_amt, max_amt - min_amt)
                tax += taxable_in_slab * pct
                
        return tax.quantize(Decimal('0.01'))


class AttendancePayrollService:
    """
    Service to calculate working days, absences, half-days, and overtime for payroll integration.
    """
    @staticmethod
    def calculate_attendance_summary(employee, year, month):
        # 1. Calculate working days in month
        start_date = datetime.date(year, month, 1)
        if month == 12:
            end_date = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            end_date = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
            
        total_days_in_month = (end_date - start_date).days + 1
        
        # Query attendance records
        records = Attendance.objects.filter(
            employee=employee,
            date__range=(start_date, end_date)
        )
        
        absent_days = Decimal(records.filter(status='ABSENT').count())
        half_days = Decimal(records.filter(status='HALF_DAY').count())
        
        # Calculate overtime hours
        overtime_hours = records.aggregate(Sum('overtime_hours'))['overtime_hours__sum'] or Decimal('0.00')
        
        # Calculate unpaid leave days
        unpaid_leaves = LeaveRequest.objects.filter(
            employee=employee,
            status='APPROVED',
            leave_type__is_paid=False,
            start_date__lte=end_date,
            end_date__gte=start_date
        )
        
        unpaid_leave_days = Decimal('0.00')
        for req in unpaid_leaves:
            # Overlap calculation
            overlap_start = max(req.start_date, start_date)
            overlap_end = min(req.end_date, end_date)
            days = (overlap_end - overlap_start).days + 1
            unpaid_leave_days += Decimal(days)
            
        return {
            'absent_days': absent_days,
            'half_days': half_days,
            'overtime_hours': Decimal(overtime_hours),
            'unpaid_leave_days': unpaid_leave_days,
            'total_days_in_month': total_days_in_month
        }


class PayrollCalculationService:
    """
    Calculates detailed earnings, deductions, and net payouts using precise Decimal formulas.
    """
    @classmethod
    def calculate_employee_payroll(cls, employee, payroll_cycle):
        structure = getattr(employee, 'salary_structure', None)
        if not structure or structure.status != 'ACTIVE':
            return None

        year = payroll_cycle.year
        month = payroll_cycle.month

        # Fetch attendance/leave metrics
        attendance_summary = AttendancePayrollService.calculate_attendance_summary(employee, year, month)
        
        # Basic earnings
        basic = structure.basic_salary
        hra = structure.hra
        
        # Allowances (M2M)
        allowances_sum = Decimal('0.00')
        for emp_allowance in structure.employeeallowance_set.all():
            allowances_sum += emp_allowance.amount
            
        # Overtime
        overtime_pay = (attendance_summary['overtime_hours'] * structure.overtime_rate).quantize(Decimal('0.01'))
        
        # Reimbursements (unpaid, approved claims)
        reimbursement_amt = Reimbursement.objects.filter(
            employee=employee,
            approval_status='APPROVED',
            created_at__year=year,
            created_at__month=month
        ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        
        # Payroll Adjustments
        adjustments = PayrollAdjustment.objects.filter(
            employee=employee,
            payroll_cycle=payroll_cycle
        )
        bonus_amt = adjustments.filter(type='EARNING').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        deductions_adj_amt = adjustments.filter(type='DEDUCTION').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

        # Absent and unpaid leave deductions
        # Deduct basic salary per-day
        daily_rate = basic / Decimal(attendance_summary['total_days_in_month'])
        leave_deduction = (
            (attendance_summary['absent_days'] * daily_rate) +
            (attendance_summary['unpaid_leave_days'] * daily_rate) +
            (attendance_summary['half_days'] * daily_rate * Decimal('0.5'))
        ).quantize(Decimal('0.01'))

        # Tax calculations
        taxable_earnings = basic + hra + allowances_sum + overtime_pay + bonus_amt - leave_deduction
        tax_amount = TaxCalculationService.calculate_tax(employee, max(taxable_earnings, Decimal('0.00')))

        # PF and ESI contributions
        pf_amount = (basic * (structure.pf_percentage / Decimal('100.00'))).quantize(Decimal('0.01'))
        esi_amount = (basic * (structure.esi_percentage / Decimal('100.00'))).quantize(Decimal('0.01'))

        # Summarize
        gross_salary = basic + hra + allowances_sum + bonus_amt + overtime_pay + reimbursement_amt
        total_deductions = tax_amount + pf_amount + esi_amount + leave_deduction + deductions_adj_amt
        net_salary = max(gross_salary - total_deductions, Decimal('0.00'))

        return {
            'basic_salary': basic,
            'hra': hra,
            'allowances': allowances_sum,
            'overtime_amount': overtime_pay,
            'reimbursement_amount': reimbursement_amt,
            'bonus_amount': bonus_amt,
            'leave_deduction': leave_deduction,
            'tax_amount': tax_amount,
            'pf_amount': pf_amount + esi_amount, # Combine standard deductions
            'deductions': total_deductions,
            'gross_salary': gross_salary,
            'net_salary': net_salary
        }


class PayrollGenerationService:
    """
    Handles bulk generation of monthly payroll records in an atomic transaction.
    """
    @classmethod
    @transaction.atomic
    def generate_monthly_payroll(cls, startup, month, year):
        # 1. Fetch or create Payroll Cycle
        payroll, created = Payroll.objects.get_or_create(
            startup=startup,
            month=month,
            year=year,
            defaults={'status': 'DRAFT'}
        )

        # Lock the row for update to prevent concurrent modification/generation
        payroll = Payroll.objects.select_for_update().get(id=payroll.id)

        if payroll.status not in ['DRAFT', 'REJECTED']:
            raise ValueError("Payroll is already processed or locked.")

        # 2. Get active employees in startup
        employees = Employee.objects.filter(startup=startup, status='ACTIVE')
        generated_count = 0

        for emp in employees:
            calc_data = PayrollCalculationService.calculate_employee_payroll(emp, payroll)
            if not calc_data:
                continue

            # Update or create PayrollRecord
            record, _ = PayrollRecord.objects.update_or_create(
                employee=emp,
                payroll_cycle=payroll,
                defaults={
                    'gross_salary': calc_data['gross_salary'],
                    'deductions': calc_data['deductions'],
                    'net_salary': calc_data['net_salary'],
                    'tax_amount': calc_data['tax_amount'],
                    'pf_amount': calc_data['pf_amount'],
                    'overtime_amount': calc_data['overtime_amount'],
                    'leave_deduction': calc_data['leave_deduction'],
                    'reimbursement_amount': calc_data['reimbursement_amount'],
                    'bonus_amount': calc_data['bonus_amount'],
                    'status': 'PENDING'
                }
            )

            # Update or create default Payslip record
            Payslip.objects.update_or_create(
                payroll=payroll,
                employee=emp,
                defaults={
                    'payroll_record': record,
                    'basic_salary': calc_data['basic_salary'],
                    'total_allowances': calc_data['hra'] + calc_data['allowances'] + calc_data['overtime_amount'] + calc_data['reimbursement_amount'] + calc_data['bonus_amount'],
                    'total_deductions': calc_data['deductions'],
                    'net_salary': calc_data['net_salary'],
                    'is_published': False
                }
            )
            generated_count += 1

        payroll.status = 'PROCESSED'
        payroll.processed_at = timezone.now()
        payroll.save()

        return payroll, generated_count


class PayrollApprovalService:
    """
    Manages payroll approval flows, status transitions, and final payout locks.
    """
    @classmethod
    @transaction.atomic
    def approve_payroll_cycle(cls, payroll_id, approver_user_id):
        # Load and lock the payroll object using select_for_update()
        payroll = Payroll.objects.select_for_update().get(id=payroll_id)

        if payroll.status == 'APPROVED':
            pass
        elif payroll.status != 'PROCESSED':
            raise ValueError(f"Only processed payrolls can be approved. Current status is: {payroll.status}")

        from django.contrib.auth import get_user_model
        User = get_user_model()
        approver_user = User.objects.get(id=approver_user_id)

        payroll.status = 'APPROVED'
        payroll.approved_by = approver_user
        payroll.save()

        # Update all records to Approved
        payroll.records.all().update(status='APPROVED')

        # Publish all associated payslips and trigger PDFs
        payslips = payroll.payslips.all()
        payslips.update(is_published=True)

        for ps in payslips:
            PayslipGenerationService.async_generate_payslip_pdf(ps)

        # Mark paid reimbursements
        Reimbursement.objects.filter(
            employee__startup=payroll.startup,
            approval_status='APPROVED',
            created_at__year=payroll.year,
            created_at__month=payroll.month
        ).update(approval_status='PAID')

        return True

    @classmethod
    @transaction.atomic
    def reject_payroll_cycle(cls, payroll_id):
        # Load and lock the payroll object using select_for_update()
        payroll = Payroll.objects.select_for_update().get(id=payroll_id)

        if payroll.status == 'REJECTED':
            pass
        elif payroll.status != 'PROCESSED':
            raise ValueError(f"Only processed payrolls can be rejected. Current status is: {payroll.status}")

        payroll.status = 'REJECTED'
        payroll.save()

        payroll.records.all().update(status='REJECTED')
        return True


class PayslipGenerationService:
    """
    Generates enterprise-grade PDF payslips branded per-organization.
    Falls back to plain text if ReportLab is unavailable.
    """

    CURRENCY_SYMBOLS = {
        'INR': '\u20b9',   # ₹
        'USD': '$',
        'EUR': '\u20ac',   # €
        'GBP': '\u00a3',   # £
        'JPY': '\u00a5',   # ¥
        'AUD': 'A$',
        'CAD': 'C$',
    }

    @staticmethod
    def _get_currency_symbol(payslip):
        """
        Reads the currency code from PayrollSetting for the startup
        and returns the matching symbol.  Defaults to ₹ (INR).
        """
        startup = payslip.employee.startup or payslip.payroll.startup
        if startup:
            try:
                setting = PayrollSetting.objects.filter(startup=startup).first()
                if setting and setting.currency:
                    return PayslipGenerationService.CURRENCY_SYMBOLS.get(
                        setting.currency.upper(),
                        setting.currency  # fallback: show the raw code
                    )
            except Exception:
                pass
        return '\u20b9'  # default ₹

    @staticmethod
    def _get_org_context(payslip):
        """
        Resolves the organisation / startup details for branding.
        Returns a dict with keys: company_name, address, tax_id, website.
        """
        org = getattr(payslip.employee, 'organization', None)
        startup = payslip.employee.startup or payslip.payroll.startup

        if org:
            return {
                'company_name': org.name or (startup.name if startup else 'Your Company'),
                'address': org.address or '',
                'tax_id': getattr(org, 'tax_id', '') or '',
                'website': org.website or (startup.website_url if startup else ''),
            }

        return {
            'company_name': startup.name if startup else 'Your Company',
            'address': '',
            'tax_id': '',
            'website': startup.website_url if startup else '',
        }

    @staticmethod
    def _month_name(month_number):
        """Convert month integer to human-readable name."""
        import calendar
        try:
            return calendar.month_name[int(month_number)]
        except (ValueError, IndexError):
            return str(month_number)

    @staticmethod
    def async_generate_payslip_pdf(payslip):
        """
        Generates a premium organisation-branded ReportLab PDF.
        Falls back to plain-text if ReportLab is missing or fails.
        """
        from io import BytesIO
        from django.core.files.base import ContentFile

        ctx = PayslipGenerationService._get_org_context(payslip)
        cur = PayslipGenerationService._get_currency_symbol(payslip)
        month_name = PayslipGenerationService._month_name(payslip.payroll.month)
        pay_period = f"{month_name} {payslip.payroll.year}"

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
            )
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

            BRAND = colors.HexColor('#0f766e')
            DARK  = colors.HexColor('#1e293b')
            GRAY  = colors.HexColor('#475569')
            LIGHT = colors.HexColor('#f1f5f9')
            BG    = colors.HexColor('#f8fafc')

            buffer = BytesIO()
            doc = SimpleDocTemplate(
                buffer, pagesize=A4,
                leftMargin=20*mm, rightMargin=20*mm,
                topMargin=18*mm, bottomMargin=18*mm,
            )
            styles = getSampleStyleSheet()
            story = []

            # ── Custom paragraph styles ──────────────────────────────────
            company_name_style = ParagraphStyle(
                'CompanyName', parent=styles['Heading1'],
                fontName='Helvetica-Bold', fontSize=18, leading=22,
                textColor=BRAND, alignment=TA_LEFT,
            )
            subtitle_style = ParagraphStyle(
                'Subtitle', parent=styles['Normal'],
                fontName='Helvetica', fontSize=9, leading=12,
                textColor=GRAY, alignment=TA_LEFT,
            )
            doc_title_style = ParagraphStyle(
                'DocTitle', parent=styles['Heading2'],
                fontName='Helvetica-Bold', fontSize=14, leading=18,
                textColor=DARK, alignment=TA_CENTER,
                spaceBefore=6, spaceAfter=4,
            )
            section_style = ParagraphStyle(
                'SectionHead', parent=styles['Heading3'],
                fontName='Helvetica-Bold', fontSize=11, leading=15,
                textColor=DARK, spaceBefore=8, spaceAfter=4,
            )
            label_style = ParagraphStyle(
                'Label', parent=styles['Normal'],
                fontName='Helvetica-Bold', fontSize=9, leading=13,
                textColor=DARK,
            )
            value_style = ParagraphStyle(
                'Value', parent=styles['Normal'],
                fontName='Helvetica', fontSize=9, leading=13,
                textColor=GRAY,
            )
            table_header_style = ParagraphStyle(
                'THead', parent=styles['Normal'],
                fontName='Helvetica-Bold', fontSize=9, leading=13,
                textColor=colors.white,
            )
            table_header_right = ParagraphStyle(
                'THeadR', parent=table_header_style, alignment=TA_RIGHT,
            )
            cell_style = ParagraphStyle(
                'TCell', parent=styles['Normal'],
                fontName='Helvetica', fontSize=9, leading=13,
                textColor=GRAY,
            )
            cell_right = ParagraphStyle(
                'TCellR', parent=cell_style, alignment=TA_RIGHT,
            )
            cell_bold = ParagraphStyle(
                'TCellB', parent=cell_style,
                fontName='Helvetica-Bold', textColor=DARK,
            )
            cell_bold_right = ParagraphStyle(
                'TCellBR', parent=cell_bold, alignment=TA_RIGHT,
            )
            footer_style = ParagraphStyle(
                'Footer', parent=styles['Normal'],
                fontName='Helvetica-Oblique', fontSize=8, leading=11,
                textColor=GRAY, alignment=TA_CENTER,
            )

            # ═══════════════════════════════════════════════════════════════
            # COMPANY HEADER
            # ═══════════════════════════════════════════════════════════════
            story.append(Paragraph(ctx['company_name'], company_name_style))

            sub_parts = []
            if ctx['address']:
                sub_parts.append(ctx['address'].replace('\n', ', '))
            if ctx['tax_id']:
                sub_parts.append(f"Tax ID: {ctx['tax_id']}")
            if ctx['website']:
                sub_parts.append(ctx['website'])
            if sub_parts:
                story.append(Paragraph(' &nbsp;|&nbsp; '.join(sub_parts), subtitle_style))

            story.append(Spacer(1, 4))
            story.append(HRFlowable(
                width="100%", thickness=1.5, color=BRAND,
                spaceAfter=10, spaceBefore=4,
            ))

            # ═══════════════════════════════════════════════════════════════
            # DOCUMENT TITLE
            # ═══════════════════════════════════════════════════════════════
            story.append(Paragraph(f"PAYSLIP &mdash; {pay_period}", doc_title_style))
            story.append(Spacer(1, 10))

            # ═══════════════════════════════════════════════════════════════
            # EMPLOYEE INFORMATION
            # ═══════════════════════════════════════════════════════════════
            story.append(Paragraph("Employee Information", section_style))

            emp = payslip.employee
            designation_text = str(emp.designation) if emp.designation else 'N/A'
            department_text  = str(emp.department) if emp.department else 'N/A'

            info_data = [
                [
                    Paragraph("Employee Name", label_style),
                    Paragraph(f"{emp.first_name} {emp.last_name}", value_style),
                    Paragraph("Employee ID", label_style),
                    Paragraph(emp.employee_id or 'N/A', value_style),
                ],
                [
                    Paragraph("Designation", label_style),
                    Paragraph(designation_text, value_style),
                    Paragraph("Department", label_style),
                    Paragraph(department_text, value_style),
                ],
                [
                    Paragraph("Pay Period", label_style),
                    Paragraph(pay_period, value_style),
                    Paragraph("Date of Joining", label_style),
                    Paragraph(
                        emp.joining_date.strftime('%d %b %Y') if emp.joining_date else 'N/A',
                        value_style,
                    ),
                ],
                [
                    Paragraph("Email Address", label_style),
                    Paragraph(emp.email or 'N/A', value_style),
                    Paragraph("", label_style),
                    Paragraph("", value_style),
                ],
            ]
            col_w = [90, 160, 90, 160]
            info_table = Table(info_data, colWidths=col_w)
            info_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LINEBELOW', (0, 0), (-1, -1), 0.4, LIGHT),
            ]))
            story.append(info_table)
            story.append(Spacer(1, 14))

            # ═══════════════════════════════════════════════════════════════
            # EARNINGS & DEDUCTIONS
            # ═══════════════════════════════════════════════════════════════
            story.append(Paragraph("Earnings &amp; Deductions", section_style))

            record = payslip.payroll_record
            tax_amt = record.tax_amount if record else Decimal('0.00')
            leave_ded = record.leave_deduction if record else Decimal('0.00')
            
            # Split PF & ESI from record.pf_amount dynamically using the ratios
            pf_calc = Decimal('0.00')
            esi_calc = Decimal('0.00')
            if record and record.pf_amount > 0:
                structure = getattr(emp, 'salary_structure', None)
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

            # Calculate HRA and special allowances from SalaryStructure
            structure = getattr(emp, 'salary_structure', None)
            hra_val = structure.hra if structure else Decimal('0.00')
            
            special_allowances = payslip.total_allowances - hra_val
            if record:
                special_allowances -= (record.overtime_amount + record.reimbursement_amount + record.bonus_amount)
            if special_allowances < 0:
                special_allowances = Decimal('0.00')

            # Build detailed earnings & deductions data
            pay_data = [
                [Paragraph("Component", table_header_style), Paragraph("Amount", table_header_right)],
                [Paragraph("Basic Salary", cell_style), Paragraph(f"{cur}{payslip.basic_salary:,.2f}", cell_right)],
            ]

            if hra_val > 0:
                pay_data.append([
                    Paragraph("House Rent Allowance (HRA)", cell_style),
                    Paragraph(f"{cur}{hra_val:,.2f}", cell_right)
                ])

            if special_allowances > 0:
                pay_data.append([
                    Paragraph("Special/Other Allowances", cell_style),
                    Paragraph(f"{cur}{special_allowances:,.2f}", cell_right)
                ])

            if record and record.overtime_amount > 0:
                pay_data.append([
                    Paragraph("Overtime Pay", cell_style),
                    Paragraph(f"{cur}{record.overtime_amount:,.2f}", cell_right)
                ])

            if record and record.reimbursement_amount > 0:
                pay_data.append([
                    Paragraph("Reimbursements", cell_style),
                    Paragraph(f"{cur}{record.reimbursement_amount:,.2f}", cell_right)
                ])

            if record and record.bonus_amount > 0:
                pay_data.append([
                    Paragraph("Bonus / Incentives", cell_style),
                    Paragraph(f"{cur}{record.bonus_amount:,.2f}", cell_right)
                ])

            # Deductions
            if tax_amt > 0:
                pay_data.append([
                    Paragraph("Income Tax (TDS)", cell_style),
                    Paragraph(f"&minus; {cur}{tax_amt:,.2f}", cell_right)
                ])

            if pf_calc > 0:
                pay_data.append([
                    Paragraph("Provident Fund (PF)", cell_style),
                    Paragraph(f"&minus; {cur}{pf_calc:,.2f}", cell_right)
                ])

            if esi_calc > 0:
                pay_data.append([
                    Paragraph("Employee State Insurance (ESI)", cell_style),
                    Paragraph(f"&minus; {cur}{esi_calc:,.2f}", cell_right)
                ])

            if leave_ded > 0:
                pay_data.append([
                    Paragraph("Absence / LOP Deductions", cell_style),
                    Paragraph(f"&minus; {cur}{leave_ded:,.2f}", cell_right)
                ])

            if other_ded > 0:
                pay_data.append([
                    Paragraph("Other Deductions", cell_style),
                    Paragraph(f"&minus; {cur}{other_ded:,.2f}", cell_right)
                ])

            # Net pay row
            pay_data.append([
                Paragraph("Net Pay", cell_bold),
                Paragraph(f"{cur}{payslip.net_salary:,.2f}", cell_bold_right),
            ])

            pay_table = Table(pay_data, colWidths=[340, 160])
            pay_table.setStyle(TableStyle([
                # Header row
                ('BACKGROUND', (0, 0), (-1, 0), BRAND),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                # Zebra striping alternate backgrounds
                ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, BG]),
                # Net-pay highlight
                ('BACKGROUND', (0, -1), (-1, -1), LIGHT),
                ('LINEABOVE', (0, -1), (-1, -1), 1.2, BRAND),
                # Subtle row borders
                ('LINEBELOW', (0, 0), (-1, -2), 0.4, LIGHT),
            ]))
            story.append(pay_table)
            story.append(Spacer(1, 20))

            # ═══════════════════════════════════════════════════════════════
            # FOOTER
            # ═══════════════════════════════════════════════════════════════
            story.append(HRFlowable(
                width="100%", thickness=0.5, color=LIGHT,
                spaceAfter=8, spaceBefore=4,
            ))
            story.append(Paragraph(
                "This is a system-generated payslip and does not require a signature.",
                footer_style,
            ))
            story.append(Paragraph(
                f"&copy; {payslip.payroll.year} {ctx['company_name']}. All rights reserved.",
                footer_style,
            ))

            # ── Build PDF ─────────────────────────────────────────────────
            doc.build(story)
            buffer.seek(0)

            payslip.pdf_file.save(
                f"payslip_{emp.id}_{payslip.payroll.year}_{payslip.payroll.month}.pdf",
                ContentFile(buffer.getvalue()),
            )
            payslip.save()

        except Exception as e:
            # ── Fallback: plain-text payslip ──────────────────────────────
            print(f"ReportLab PDF generation failed ({e}), falling back to text.")
            try:
                designation_text = str(payslip.employee.designation) if payslip.employee.designation else 'N/A'
                department_text  = str(payslip.employee.department) if payslip.employee.department else 'N/A'
                buffer = BytesIO()
                
                earnings_str = f"  Basic Salary       {cur}{payslip.basic_salary:,.2f}\n"
                if hra_val > 0:
                    earnings_str += f"  HRA                {cur}{hra_val:,.2f}\n"
                if special_allowances > 0:
                    earnings_str += f"  Other Allowances   {cur}{special_allowances:,.2f}\n"
                if record and record.overtime_amount > 0:
                    earnings_str += f"  Overtime Pay       {cur}{record.overtime_amount:,.2f}\n"
                if record and record.reimbursement_amount > 0:
                    earnings_str += f"  Reimbursements     {cur}{record.reimbursement_amount:,.2f}\n"
                if record and record.bonus_amount > 0:
                    earnings_str += f"  Bonus/Incentive    {cur}{record.bonus_amount:,.2f}\n"

                deductions_str = ""
                if tax_amt > 0:
                    deductions_str += f"  Income Tax (TDS)   {cur}{tax_amt:,.2f}\n"
                if pf_calc > 0:
                    deductions_str += f"  Provident Fund     {cur}{pf_calc:,.2f}\n"
                if esi_calc > 0:
                    deductions_str += f"  ESI                {cur}{esi_calc:,.2f}\n"
                if leave_ded > 0:
                    deductions_str += f"  Absence Deductions {cur}{leave_ded:,.2f}\n"
                if other_ded > 0:
                    deductions_str += f"  Other Deductions   {cur}{other_ded:,.2f}\n"

                content = f"""========================================================================
            {ctx['company_name'].upper()} — PAYSLIP
========================================================================
Pay Period : {pay_period}
Employee   : {payslip.employee.first_name} {payslip.employee.last_name}
Employee ID: {payslip.employee.employee_id or 'N/A'}
Designation: {designation_text}
Department : {department_text}
------------------------------------------------------------------------
EARNINGS:
{earnings_str}------------------------------------------------------------------------
DEDUCTIONS:
{deductions_str}  Total Deductions   {cur}{payslip.total_deductions:,.2f}
------------------------------------------------------------------------
NET PAY              {cur}{payslip.net_salary:,.2f}
========================================================================
This is a system-generated payslip. No signature required.
(c) {payslip.payroll.year} {ctx['company_name']}
========================================================================
"""
                buffer.write(content.encode('utf-8'))
                buffer.seek(0)

                payslip.pdf_file.save(
                    f"payslip_{payslip.employee.id}_{payslip.payroll.year}_{payslip.payroll.month}.txt",
                    ContentFile(buffer.getvalue()),
                )
                payslip.save()
            except Exception as ex:
                print(f"Error generating fallback payslip file: {ex}")

