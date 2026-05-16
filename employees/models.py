import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from maincore.basemodel import SoftDeleteModel

class Employee(SoftDeleteModel):
    """
    Core employee model. Connects to User (nullable) and Startup.
    """
    EMPLOYMENT_TYPE_CHOICES = (
        ('FULL_TIME', 'Full Time'),
        ('PART_TIME', 'Part Time'),
        ('CONTRACT', 'Contract'),
        ('INTERN', 'Intern'),
    )
    
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('ON_BOARDING', 'On Boarding'),
        ('EXITED', 'Exited'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='employees',
        db_index=True,
        null=True,
        blank=True
    )
    organization = models.ForeignKey(
        'organization.Organization',
        on_delete=models.CASCADE,
        related_name='employees',
        db_index=True,
        null=True,
        blank=True
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee_profile'
    )
    employee_id = models.CharField(max_length=50, db_index=True)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=20, blank=True)
    
    designation = models.ForeignKey(
        'organization.Designation',
        on_delete=models.SET_NULL,
        null=True,
        related_name='employees'
    )
    department = models.ForeignKey(
        'organization.Department',
        on_delete=models.SET_NULL,
        null=True,
        related_name='employees'
    )
    
    joining_date = models.DateField(null=True, blank=True)
    employment_type = models.CharField(
        max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default='FULL_TIME'
    )
    reporting_manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subordinates'
    )
    salary = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    avatar = models.URLField(max_length=500, blank=True, null=True)
    
    # Tracking
    job_application = models.OneToOneField(
        'jobs.JobApplication',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hired_employee'
    )
    address = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='ON_BOARDING'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        unique_together = ('startup', 'employee_id')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_id})"

    def save(self, *args, **kwargs):
        if not self.employee_id or self.employee_id == 'TEMP-ID':
            prefix = "EMP"
            # Filter by startup or organization to ensure serial is per tenant
            qs = Employee.all_objects.filter(employee_id__startswith=f"{prefix}-")
            if self.organization:
                qs = qs.filter(organization=self.organization)
            elif self.startup:
                qs = qs.filter(startup=self.startup)
                
            last_employee = qs.order_by('created_at').last()
            if last_employee:
                try:
                    last_id_num = int(last_employee.employee_id.split('-')[1])
                    self.employee_id = f"{prefix}-{last_id_num + 1:04d}"
                except (IndexError, ValueError):
                    count = qs.count()
                    self.employee_id = f"{prefix}-{count + 1:04d}"
            else:
                self.employee_id = f"{prefix}-0001"
        super().save(*args, **kwargs)

class EmployeeProfile(models.Model):
    """
    Additional profile details for an employee.
    """
    employee = models.OneToOneField(
        Employee, on_delete=models.CASCADE, related_name='profile_details'
    )
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    marital_status = models.CharField(max_length=20, blank=True)
    blood_group = models.CharField(max_length=10, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    personal_email = models.EmailField(blank=True)
    pan_number = models.CharField(max_length=20, blank=True)
    aadhaar_number = models.CharField(max_length=20, blank=True)
    bank_name = models.CharField(max_length=255, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    ifsc_code = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"Profile for {self.employee}"

class EmergencyContact(models.Model):
    """
    Emergency contact details for an employee.
    """
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='emergency_contacts'
    )
    name = models.CharField(max_length=255)
    relationship = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    alt_phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.relationship}) for {self.employee}"

class EmployeeDocument(models.Model):
    """
    Documents uploaded for an employee (e.g., ID proof, Offer Letter).
    """
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='documents'
    )
    document_name = models.CharField(max_length=255)
    document_type = models.CharField(max_length=100)
    file_url = models.URLField(max_length=500)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.document_name} for {self.employee}"
