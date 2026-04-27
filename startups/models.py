import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from maincore.basemodel import SoftDeleteModel


class CompanyProfile(SoftDeleteModel):
    """
    Company profile linked to a registered user.
    Any authenticated user can register a company to start posting jobs.
    """

    COMPANY_SIZE_CHOICES = (
        ("1-10", "1-10 employees"),
        ("11-50", "11-50 employees"),
        ("51-200", "51-200 employees"),
        ("201-500", "201-500 employees"),
        ("500+", "500+ employees"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company_profile",
        db_index=True,
        null=True,
        blank=True,
    )
    company_name = models.CharField(max_length=255, db_index=True)
    company_email = models.EmailField(unique=True, db_index=True, null=True, blank=True)
    company_password = models.CharField(max_length=128, null=True, blank=True)
    logo_url = models.URLField(max_length=500, blank=True)
    banner_url = models.URLField(max_length=500, blank=True)
    industry = models.CharField(max_length=150, db_index=True)
    company_size = models.CharField(
        max_length=20, choices=COMPANY_SIZE_CHOICES, default="1-10"
    )
    description = models.TextField(blank=True)
    website = models.URLField(max_length=255, blank=True)
    founded_year = models.PositiveIntegerField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    is_approved = models.BooleanField(default=False)
    is_genuine = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company Profile"
        verbose_name_plural = "Company Profiles"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company_name} ({self.company_email or (self.owner.email if self.owner else 'No email')})"

    def set_password(self, raw_password):
        self.company_password = make_password(raw_password)

    def check_company_password(self, raw_password):
        return check_password(raw_password, self.company_password)


class CompanyHRProfile(SoftDeleteModel):
    """
    HR profile details for a company.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.OneToOneField(
        CompanyProfile, on_delete=models.CASCADE, related_name="hr_profile", db_index=True
    )
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    designation = models.CharField(max_length=150, blank=True)
    profile_image_url = models.URLField(max_length=500, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company HR Profile"
        verbose_name_plural = "Company HR Profiles"

    def __str__(self):
        return f"HR for {self.company.company_name} - {self.name or 'No Name'}"


class Startup(SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    founder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="startups",
        db_index=True,
    )
    name = models.CharField(max_length=255, db_index=True)
    pitch = models.TextField()
    industry = models.CharField(max_length=150, db_index=True)
    stage = models.CharField(
        max_length=100, help_text="e.g. Concept, MVP, Seed, Series A"
    )
    seeking_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    website_url = models.URLField(max_length=255, blank=True)
    logo_url = models.URLField(max_length=500, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Startup"
        verbose_name_plural = "Startups"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} (by {self.founder.email})"
