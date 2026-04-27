import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from maincore.basemodel import SoftDeleteModel



class JobPost(SoftDeleteModel):
    """
    A job listing posted by a company.
    """

    JOB_TYPE_CHOICES = (
        ("FULL_TIME", "Full Time"),
        ("PART_TIME", "Part Time"),
        ("CONTRACT", "Contract"),
        ("INTERNSHIP", "Internship"),
    )

    WORK_MODE_CHOICES = (
        ("REMOTE", "Remote"),
        ("ONSITE", "On-site"),
        ("HYBRID", "Hybrid"),
    )

    EXPERIENCE_LEVEL_CHOICES = (
        ("ENTRY", "Entry Level"),
        ("MID", "Mid Level"),
        ("SENIOR", "Senior Level"),
        ("LEAD", "Lead / Principal"),
    )

    STATUS_CHOICES = (
        ("DRAFT", "Draft"),
        ("ACTIVE", "Active"),
        ("CLOSED", "Closed"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        'startups.CompanyProfile',
        on_delete=models.CASCADE,
        related_name="job_posts",
        db_index=True,
    )
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField()
    location = models.CharField(max_length=200, blank=True)
    job_type = models.CharField(
        max_length=20, choices=JOB_TYPE_CHOICES, default="FULL_TIME"
    )
    work_mode = models.CharField(
        max_length=20, choices=WORK_MODE_CHOICES, default="ONSITE"
    )
    salary_min = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    salary_max = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(max_length=10, default="INR")
    skills_required = models.JSONField(default=list, blank=True)
    experience_level = models.CharField(
        max_length=20, choices=EXPERIENCE_LEVEL_CHOICES, default="ENTRY"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="DRAFT", db_index=True
    )
    deadline = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Job Post"
        verbose_name_plural = "Job Posts"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} at {self.company.company_name}"

    @property
    def applications_count(self):
        return getattr(self, '_applications_count', self.applications.filter(is_deleted=False).count())

    @applications_count.setter
    def applications_count(self, value):
        self._applications_count = value


class JobApplication(SoftDeleteModel):
    """
    An application submitted by a user to a specific job post.
    """

    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("REVIEWED", "Reviewed"),
        ("SHORTLISTED", "Shortlisted"),
        ("REJECTED", "Rejected"),
        ("HIRED", "Hired"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        JobPost,
        on_delete=models.CASCADE,
        related_name="applications",
        db_index=True,
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="job_applications",
        db_index=True,
    )
    resume_url = models.URLField(max_length=500, blank=True)
    cover_letter = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="PENDING", db_index=True
    )

    applied_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Job Application"
        verbose_name_plural = "Job Applications"
        ordering = ["-applied_at"]
        unique_together = ("job", "applicant")

    def __str__(self):
        return f"{self.applicant.email} → {self.job.title}"
