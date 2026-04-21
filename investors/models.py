import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from maincore.basemodel import SoftDeleteModel

class Investor(SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='investor_profile'
    )
    headline = models.CharField(max_length=255, blank=True, help_text="Short professional headline")
    bio = models.TextField(blank=True)
    location = models.CharField(max_length=100, blank=True)
    profile_image_url = models.URLField(max_length=500, blank=True)
    banner_image_url = models.URLField(max_length=500, blank=True)
    firm_name = models.CharField(max_length=255, blank=True)
    preferred_stages = models.JSONField(default=list, blank=True, help_text="e.g. Pre-seed, Seed, Series A")
    preferred_industries = models.JSONField(default=list, blank=True, help_text="e.g. AI, FinTech, HealthTech")
    minimum_investment_range = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    maximum_investment_range = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    linkedin_url = models.URLField(max_length=255, blank=True)
    portfolio_url = models.URLField(max_length=255, blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Investor'
        verbose_name_plural = 'Investors'

    def __str__(self):
        return f"Investor: {self.firm_name or self.user.email}"
