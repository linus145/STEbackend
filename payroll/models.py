import uuid
from django.db import models
from django.utils import timezone
from django.conf import settings
from maincore.basemodel import SoftDeleteModel

class Allowance(SoftDeleteModel):
    """
    Standard allowances (e.g., HRA, Transport, Bonus).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='allowances'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_taxable = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} - {self.startup.name}"

class Deduction(SoftDeleteModel):
    """
    Standard deductions (e.g., Professional Tax, Insurance, Loan).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='deductions'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.name} - {self.startup.name}"

class SalaryStructure(SoftDeleteModel):
    """
    The breakdown of an employee's salary with detailed percentages and overtime settings.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.OneToOneField(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='salary_structure'
    )
    basic_salary = models.DecimalField(max_digits=15, decimal_places=2)
    hra = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="House Rent Allowance")
    overtime_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Overtime rate per hour")
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Default tax deduction percentage")
    pf_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Provident Fund percentage")
    esi_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Employee State Insurance percentage")
    effective_from = models.DateField(default=timezone.now)
    status = models.CharField(
        max_length=20, 
        choices=[('ACTIVE', 'Active'), ('INACTIVE', 'Inactive')], 
        default='ACTIVE'
    )
    
    # Many-to-Many with through models to store fixed amounts per employee
    allowances = models.ManyToManyField(Allowance, through='EmployeeAllowance')
    deductions = models.ManyToManyField(Deduction, through='EmployeeDeduction')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Salary Structure for {self.employee}"

class EmployeeAllowance(models.Model):
    structure = models.ForeignKey(SalaryStructure, on_delete=models.CASCADE)
    allowance = models.ForeignKey(Allowance, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=15, decimal_places=2)

class EmployeeDeduction(models.Model):
    structure = models.ForeignKey(SalaryStructure, on_delete=models.CASCADE)
    deduction = models.ForeignKey(Deduction, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=15, decimal_places=2)

class Payroll(SoftDeleteModel):
    """
    Monthly payroll generation for a startup.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'), 
        ('PROCESSED', 'Processed'), 
        ('APPROVED', 'Approved'),
        ('PAID', 'Paid'),
        ('REJECTED', 'Rejected')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='payrolls'
    )
    month = models.IntegerField()
    year = models.IntegerField()
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES,
        default='DRAFT'
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_payrolls'
    )
    
    class Meta:
        unique_together = ('startup', 'month', 'year')

    def __str__(self):
        return f"Payroll {self.month}/{self.year} - {self.startup.name}"

class PayrollRecord(SoftDeleteModel):
    """
    Individual calculation record for an employee for a specific payroll cycle.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('PAID', 'Paid')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='payroll_records'
    )
    payroll_cycle = models.ForeignKey(
        Payroll,
        on_delete=models.CASCADE,
        related_name='records'
    )
    gross_salary = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    deductions = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    net_salary = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    pf_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    overtime_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    leave_deduction = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    reimbursement_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    bonus_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('employee', 'payroll_cycle')

    def __str__(self):
        return f"Payroll Record - {self.employee} - {self.payroll_cycle.month}/{self.payroll_cycle.year}"

class Payslip(SoftDeleteModel):
    """
    Individual payslip generated from a payroll record.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payroll = models.ForeignKey(
        Payroll, on_delete=models.CASCADE, related_name='payslips'
    )
    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='payslips'
    )
    payroll_record = models.ForeignKey(
        PayrollRecord, on_delete=models.CASCADE, null=True, blank=True, related_name='payslips'
    )
    
    # Calculated values at the time of generation
    basic_salary = models.DecimalField(max_digits=15, decimal_places=2)
    total_allowances = models.DecimalField(max_digits=15, decimal_places=2)
    total_deductions = models.DecimalField(max_digits=15, decimal_places=2)
    net_salary = models.DecimalField(max_digits=15, decimal_places=2)
    
    pdf_file = models.FileField(upload_to='payslips/', null=True, blank=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    generated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Payslip for {self.employee} - {self.payroll}"

class Reimbursement(SoftDeleteModel):
    """
    Employee expense claims that need approval and dynamic payout in payroll.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('PAID', 'Paid')
    ]
    CATEGORY_CHOICES = [
        ('TRAVEL', 'Travel & Commute'),
        ('MEALS', 'Meals & Entertainment'),
        ('EQUIPMENT', 'Office Equipment & Gadgets'),
        ('UTILITIES', 'Internet & Utilities'),
        ('OTHER', 'Other Expenses')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='reimbursements'
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='OTHER')
    description = models.TextField(blank=True)
    proof = models.FileField(upload_to='reimbursement_proofs/', null=True, blank=True)
    approval_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.category} - {self.amount} - {self.employee}"

class PayrollAdjustment(SoftDeleteModel):
    """
    One-off dynamic adjustments (Earning or Deduction) applied to an employee's payslip.
    """
    TYPE_CHOICES = [
        ('EARNING', 'Earning'),
        ('DEDUCTION', 'Deduction')
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='adjustments'
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    reason = models.TextField()
    payroll_cycle = models.ForeignKey(
        Payroll,
        on_delete=models.CASCADE,
        related_name='adjustments',
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type} Adjustment ({self.amount}) for {self.employee}"

class TaxConfiguration(SoftDeleteModel):
    """
    Tax slabs for income tax calculation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slab_name = models.CharField(max_length=255)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="Tax percentage")
    min_amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="Minimum income threshold")
    max_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, help_text="Maximum income threshold")
    startup = models.ForeignKey(
        'startups.Startup',
        on_delete=models.CASCADE,
        related_name='tax_configs',
        null=True,
        blank=True
    )

    def __str__(self):
        return f"{self.slab_name} ({self.percentage}%)"

class PayrollSetting(SoftDeleteModel):
    """
    Corporate settings for the payroll system (currency selection, pf, esi details).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.OneToOneField(
        'startups.Startup',
        on_delete=models.CASCADE,
        related_name='payroll_setting'
    )
    currency = models.CharField(max_length=10, default='INR', help_text="e.g. INR, USD, EUR")
    automation_enabled = models.BooleanField(default=True)
    pf_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=12.00)
    esi_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=1.75)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payroll Settings for {self.startup.name}"


class DocumentTemplate(SoftDeleteModel):
    """
    Templates for Offer Letters, Joining Letters, and Payroll summaries.
    """
    CATEGORY_CHOICES = [
        ('PAYROLL', 'Payroll Related'),
        ('OFFER_LETTER', 'Offer Letter'),
        ('JOINING_LETTER', 'Joining Letter'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup',
        on_delete=models.CASCADE,
        related_name='document_templates'
    )
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='PAYROLL')
    content = models.TextField(blank=True, help_text="Template body content in rich-text, HTML or markdown.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

