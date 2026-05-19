import uuid
from django.db import models
from django.utils import timezone
from maincore.basemodel import SoftDeleteModel

class Organization(SoftDeleteModel):
    """
    The operational business entity linked to a Startup.
    One Startup can have multiple organizations (branches, subsidiaries).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        'startups.CompanyProfile', 
        on_delete=models.CASCADE, 
        related_name='organizations',
        db_index=True,
        null=True,
        blank=True
    )
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='organizations',
        db_index=True,
        null=True,
        blank=True
    )
    name = models.CharField(max_length=255)
    tax_id = models.CharField(max_length=100, blank=True, help_text="e.g. GSTIN, EIN")
    address = models.TextField(blank=True)
    website = models.URLField(max_length=255, blank=True)
    logo_url = models.URLField(max_length=500, blank=True)
    banner_url = models.URLField(max_length=500, blank=True)
    industry = models.CharField(max_length=150, blank=True)
    company_size = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    founded_year = models.PositiveIntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        ordering = ['name']

    def __str__(self):
        startup_name = self.startup.name if self.startup else "Global"
        return f"{self.name} ({startup_name})"

class Department(SoftDeleteModel):
    """
    Departments within an Organization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='departments',
        db_index=True,
        null=True,
        blank=True
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='departments',
        null=True,
        blank=True
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        unique_together = ('organization', 'name')
        ordering = ['name']

    def __str__(self):
        org_name = self.organization.name if self.organization else (self.startup.name if self.startup else "Unknown")
        return f"{self.name} - {org_name}"

class Designation(SoftDeleteModel):
    """
    Employee designations/roles within an Organization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='designations',
        db_index=True,
        null=True,
        blank=True
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='designations',
        null=True,
        blank=True
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Designation"
        verbose_name_plural = "Designations"
        unique_together = ('organization', 'title')
        ordering = ['title']

    def __str__(self):
        org_name = self.organization.name if self.organization else (self.startup.name if self.startup else "Unknown")
        return f"{self.title} - {org_name}"
