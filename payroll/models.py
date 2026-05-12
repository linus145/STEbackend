import uuid
from django.db import models
from django.utils import timezone
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
    The breakdown of an employee's salary.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.OneToOneField(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='salary_structure'
    )
    basic_salary = models.DecimalField(max_digits=15, decimal_places=2)
    
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
        choices=[('DRAFT', 'Draft'), ('PROCESSED', 'Processed'), ('PAID', 'Paid')],
        default='DRAFT'
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ('startup', 'month', 'year')

    def __str__(self):
        return f"Payroll {self.month}/{self.year} - {self.startup.name}"

class Payslip(SoftDeleteModel):
    """
    Individual payslip generated from a payroll run.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payroll = models.ForeignKey(
        Payroll, on_delete=models.CASCADE, related_name='payslips'
    )
    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='payslips'
    )
    
    # Calculated values at the time of generation
    basic_salary = models.DecimalField(max_digits=15, decimal_places=2)
    total_allowances = models.DecimalField(max_digits=15, decimal_places=2)
    total_deductions = models.DecimalField(max_digits=15, decimal_places=2)
    net_salary = models.DecimalField(max_digits=15, decimal_places=2)
    
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payslip for {self.employee} - {self.payroll}"
