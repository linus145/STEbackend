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

    ROLE_CHOICES = (
        ('EMPLOYEE', 'Employee'),
        ('MANAGER', 'Manager'),
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
    role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default='EMPLOYEE', db_index=True
    )
    
    portal_username = models.CharField(max_length=150, unique=True, null=True, blank=True, db_index=True)
    portal_password = models.CharField(max_length=255, blank=True, default='')
    
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
        if not self.portal_username:
            base_uname = f"emp_{self.first_name.lower().replace(' ', '')}"
            unique_uname = base_uname
            counter = 1
            while Employee.all_objects.filter(portal_username=unique_uname).exists():
                unique_uname = f"{base_uname}{counter}"
                counter += 1
            self.portal_username = unique_uname

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


class EmployeeAadhaarDetail(models.Model):
    """
    Aadhaar statutory details for an employee under an organization.
    """
    employee = models.OneToOneField(
        Employee, on_delete=models.CASCADE, related_name='aadhaar_detail'
    )
    organization = models.ForeignKey(
        'organization.Organization',
        on_delete=models.CASCADE,
        related_name='aadhaar_details',
        db_index=True,
        null=True,
        blank=True
    )
    aadhaar_number = models.CharField(max_length=20, blank=True)
    enrollment_no = models.CharField(max_length=50, blank=True)
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Employee Aadhaar Detail"
        verbose_name_plural = "Employee Aadhaar Details"

    def __str__(self):
        return f"Aadhaar for {self.employee}"


class EmployeePANDetail(models.Model):
    """
    PAN statutory details for an employee under an organization.
    """
    employee = models.OneToOneField(
        Employee, on_delete=models.CASCADE, related_name='pan_detail'
    )
    organization = models.ForeignKey(
        'organization.Organization',
        on_delete=models.CASCADE,
        related_name='pan_details',
        db_index=True,
        null=True,
        blank=True
    )
    pan_number = models.CharField(max_length=20, blank=True)
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Employee PAN Detail"
        verbose_name_plural = "Employee PAN Details"

    def __str__(self):
        return f"PAN for {self.employee}"


class EmployeeJoiningDetail(models.Model):
    """
    Joining and probation details for an employee under an organization.
    """
    employee = models.OneToOneField(
        Employee, on_delete=models.CASCADE, related_name='joining_detail'
    )
    organization = models.ForeignKey(
        'organization.Organization',
        on_delete=models.CASCADE,
        related_name='joining_details',
        db_index=True,
        null=True,
        blank=True
    )
    joining_date = models.DateField(null=True, blank=True)
    probation_period = models.CharField(max_length=50, blank=True, default="3 Months")
    confirmation_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Employee Joining Detail"
        verbose_name_plural = "Employee Joining Details"

    def __str__(self):
        return f"Joining Details for {self.employee}"


class EmployeeBankDetail(models.Model):
    """
    Bank account details for salary processing under an organization.
    """
    employee = models.OneToOneField(
        Employee, on_delete=models.CASCADE, related_name='bank_detail'
    )
    organization = models.ForeignKey(
        'organization.Organization',
        on_delete=models.CASCADE,
        related_name='bank_details',
        db_index=True,
        null=True,
        blank=True
    )
    bank_name = models.CharField(max_length=150, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    ifsc_code = models.CharField(max_length=20, blank=True)
    account_holder_name = models.CharField(max_length=150, blank=True)
    branch_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Employee Bank Detail"
        verbose_name_plural = "Employee Bank Details"

    def __str__(self):
        return f"Bank details for {self.employee}"


from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Employee)
def create_employee_statutory_details(sender, instance, created, **kwargs):
    if created:
        EmployeeProfile.objects.get_or_create(
            employee=instance,
            defaults={'personal_email': instance.email}
        )
        EmployeeAadhaarDetail.objects.get_or_create(
            employee=instance,
            defaults={'organization': instance.organization}
        )
        EmployeePANDetail.objects.get_or_create(
            employee=instance,
            defaults={'organization': instance.organization}
        )
        EmployeeJoiningDetail.objects.get_or_create(
            employee=instance,
            defaults={
                'organization': instance.organization,
                'joining_date': instance.joining_date or timezone.now().date()
            }
        )
        EmployeeBankDetail.objects.get_or_create(
            employee=instance,
            defaults={'organization': instance.organization}
        )


class EmployeeUser(SoftDeleteModel):
    """
    Dedicated authentication user model for the Employee Portal.
    Completely isolates employee portal users from the customer/founder CustomUser table.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.OneToOneField(
        'Employee',
        on_delete=models.CASCADE,
        related_name='portal_user'
    )
    portal_username = models.CharField(max_length=150, unique=True, db_index=True)
    email = models.EmailField(db_index=True)
    password = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=Employee.ROLE_CHOICES, default='EMPLOYEE', db_index=True)
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'portal_username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name = "Employee User"
        verbose_name_plural = "Employee Users"
        ordering = ['-created_at']

    def __str__(self):
        emp_name = f"{self.employee.first_name} {self.employee.last_name}" if hasattr(self, 'employee') and self.employee else ""
        return f"{self.portal_username} ({emp_name})".strip()

    def check_password(self, raw_password):
        from django.contrib.auth.hashers import check_password
        return check_password(raw_password, self.password)

    def set_password(self, raw_password):
        from django.contrib.auth.hashers import make_password
        self.password = make_password(raw_password)

    def get_username(self):
        return self.portal_username

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def is_staff(self):
        return False

    @property
    def is_superuser(self):
        return False

    @property
    def employee_profile(self):
        """Duck-typing compatibility for modules referencing request.user.employee_profile"""
        try:
            return self.employee
        except Exception:
            return None

    @property
    def organization(self):
        try:
            return self.employee.organization
        except Exception:
            return None

    @property
    def startup(self):
        try:
            return self.employee.startup
        except Exception:
            return None

    @property
    def first_name(self):
        try:
            return self.employee.first_name
        except Exception:
            return ''

    @property
    def last_name(self):
        try:
            return self.employee.last_name
        except Exception:
            return ''

    @property
    def phone(self):
        try:
            return self.employee.phone
        except Exception:
            return ''

    @property
    def phone_number(self):
        try:
            return self.employee.phone
        except Exception:
            return ''

    @property
    def groups(self):
        from django.contrib.auth.models import Group
        return Group.objects.none()

    @property
    def user_permissions(self):
        from django.contrib.auth.models import Permission
        return Permission.objects.none()

    def has_perm(self, perm, obj=None):
        return False

    def has_perms(self, perm_list, obj=None):
        return False

    def has_module_perms(self, app_label):
        return False


@receiver(post_save, sender=Employee)
def sync_employee_portal_user(sender, instance, created, **kwargs):
    """
    Automatically creates or synchronizes the dedicated EmployeeUser whenever
    an Employee record is saved, ensuring complete isolation from CustomUser.
    """
    if not instance.portal_username:
        return
    try:
        emp_user = EmployeeUser.objects.filter(employee=instance).first()
        if not emp_user:
            emp_user = EmployeeUser(
                employee=instance,
                portal_username=instance.portal_username,
                email=instance.email,
                role=instance.role,
                is_active=(instance.status not in ['EXITED', 'INACTIVE']),
            )
            if instance.portal_password:
                emp_user.set_password(instance.portal_password)
            else:
                emp_user.password = ''
            emp_user.save()
        else:
            changed = False
            if emp_user.portal_username != instance.portal_username:
                emp_user.portal_username = instance.portal_username
                changed = True
            if emp_user.email != instance.email:
                emp_user.email = instance.email
                changed = True
            if emp_user.role != instance.role:
                emp_user.role = instance.role
                changed = True
            expected_active = (instance.status not in ['EXITED', 'INACTIVE'])
            if emp_user.is_active != expected_active:
                emp_user.is_active = expected_active
                changed = True
            if instance.portal_password and not emp_user.password:
                emp_user.set_password(instance.portal_password)
                changed = True
            elif instance.portal_password and not emp_user.check_password(instance.portal_password):
                # portal_password was changed on Employee record — re-sync the hash
                emp_user.set_password(instance.portal_password)
                changed = True
            if changed:
                emp_user.save()
    except Exception:
        pass

