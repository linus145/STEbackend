import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from maincore.basemodel import SoftDeleteModel


class Founder(SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='founder_profile'
    )
    headline = models.CharField(max_length=255, blank=True, help_text="Short professional headline")
    bio = models.TextField(blank=True)
    location = models.CharField(max_length=100, blank=True)
    profile_image_url = models.URLField(max_length=500, blank=True)
    experience_years = models.PositiveIntegerField(default=0)
    primary_industry = models.CharField(max_length=100, db_index=True, blank=True)
    skills = models.JSONField(default=list, blank=True)
    linkedin_url = models.URLField(max_length=255, blank=True)
    portfolio_url = models.URLField(max_length=255, blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Founder'
        verbose_name_plural = 'Founders'

    def __str__(self):
        return f"Founder: {self.user.email}"
