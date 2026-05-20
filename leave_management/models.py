import uuid
from django.db import models
from django.utils import timezone
from maincore.basemodel import SoftDeleteModel

class LeaveType(SoftDeleteModel):
    """
    Types of leave available (e.g., Annual, Sick, Casual, Occasional, National).
    """
    CATEGORY_CHOICES = (
        ('ANNUAL', 'Annual Leave'),
        ('SICK', 'Sick Leave'),
        ('CASUAL', 'Casual Leave'),
        ('OCCASIONAL', 'Occasional Leave'),
        ('NATIONAL', 'National Holiday / Leave'),
        ('OTHER', 'Other'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='leave_types',
        null=True,
        blank=True
    )
    organization = models.ForeignKey(
        'organization.Organization',
        on_delete=models.CASCADE,
        related_name='leave_types',
        null=True,
        blank=True
    )
    company = models.ForeignKey(
        'startups.CompanyProfile',
        on_delete=models.CASCADE,
        related_name='leave_types',
        null=True,
        blank=True
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='OTHER')
    is_paid = models.BooleanField(default=True)
    carry_forward = models.BooleanField(default=False)
    max_days_per_year = models.IntegerField(null=True, blank=True, default=0)
    date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        owner_name = self.organization.name if self.organization else (self.startup.name if self.startup else "Unknown")
        return f"{self.name} - {owner_name}"

class LeaveRequest(SoftDeleteModel):
    """
    Requests for leave submitted by employees.
    """
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='leave_requests',
        null=True,
        blank=True
    )
    organization = models.ForeignKey(
        'organization.Organization',
        on_delete=models.CASCADE,
        related_name='leave_requests',
        null=True,
        blank=True
    )
    company = models.ForeignKey(
        'startups.CompanyProfile',
        on_delete=models.CASCADE,
        related_name='leave_requests',
        null=True,
        blank=True
    )
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='my_leave_requests'
    )
    leave_type = models.ForeignKey(
        LeaveType,
        on_delete=models.CASCADE,
        related_name='requests'
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Approval details
    approved_by = models.ForeignKey(
        'employees.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_leaves'
    )
    comment = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.employee} - {self.leave_type.name} ({self.start_date} to {self.end_date})"

class LeaveBalance(models.Model):
    """
    Tracking available leave days for each employee.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='leave_balances'
    )
    leave_type = models.ForeignKey(
        LeaveType,
        on_delete=models.CASCADE,
        related_name='employee_balances'
    )
    year = models.IntegerField(default=timezone.now().year)
    total_days = models.DecimalField(max_digits=5, decimal_places=1, default=0.0)
    used_days = models.DecimalField(max_digits=5, decimal_places=1, default=0.0)
    
    @property
    def remaining_days(self):
        return self.total_days - self.used_days

    class Meta:
        unique_together = ('employee', 'leave_type', 'year')

    def __str__(self):
        return f"{self.employee} - {self.leave_type.name} ({self.year})"
