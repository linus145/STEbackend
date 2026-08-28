import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from maincore.basemodel import SoftDeleteModel


class CompanyPage(SoftDeleteModel):
    """
    LinkedIn-style Company Page model extending CompanyProfile with
    rich profile metadata, unique slugs, custom badges, and culture specs.
    """
    PAGE_TYPE_CHOICES = (
        ("COMPANY", "Company / Enterprise"),
        ("SMALL_BUSINESS", "Small Business (<200 employees)"),
        ("STARTUP", "Startup"),
        ("EDUCATIONAL", "Educational Institution"),
        ("NON_PROFIT", "Non-Profit Organization"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.OneToOneField(
        "startups.CompanyProfile",
        on_delete=models.CASCADE,
        related_name="page_details",
        db_index=True
    )
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    tagline = models.CharField(max_length=300, blank=True)
    page_type = models.CharField(max_length=50, choices=PAGE_TYPE_CHOICES, default="COMPANY")
    overview = models.TextField(blank=True)
    specialties = models.JSONField(default=list, blank=True)
    
    # Custom visuals (fallbacks to CompanyProfile logo_url/banner_url if empty)
    custom_banner_url = models.URLField(max_length=500, blank=True)
    custom_logo_url = models.URLField(max_length=500, blank=True)
    
    # Verification & Highlights
    is_verified = models.BooleanField(default=False)
    call_to_action_label = models.CharField(max_length=50, default="Visit website")
    call_to_action_url = models.URLField(max_length=500, blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company Page"
        verbose_name_plural = "Company Pages"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company.company_name} (/{self.slug})"

    @classmethod
    def generate_unique_slug(cls, name, instance_id=None):
        base_slug = slugify(name) or "company"
        slug = base_slug
        counter = 1
        qs = cls.all_objects.filter(slug=slug)
        if instance_id:
            qs = qs.exclude(id=instance_id)
        while qs.exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
            qs = cls.all_objects.filter(slug=slug)
            if instance_id:
                qs = qs.exclude(id=instance_id)
        return slug


class CompanyPost(SoftDeleteModel):
    """
    Dedicated post model for company pages.
    Posts created on a company page remain strictly attached to that company page,
    preventing personal user feed posts from leaking into company profiles and vice-versa.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_page = models.ForeignKey(
        CompanyPage,
        on_delete=models.CASCADE,
        related_name="company_posts",
        db_index=True
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company_page_posts",
        db_index=True
    )
    content = models.TextField()
    media_url = models.URLField(max_length=500, blank=True, null=True)
    is_promoted = models.BooleanField(default=False, db_index=True)
    
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company Post"
        verbose_name_plural = "Company Posts"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Post on {self.company_page.company.company_name} at {self.created_at}"
