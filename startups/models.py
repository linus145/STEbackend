import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from maincore.basemodel import SoftDeleteModel

class Startup(SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    founder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='startups',
        db_index=True
    )
    name = models.CharField(max_length=255, db_index=True)
    pitch = models.TextField()
    industry = models.CharField(max_length=150, db_index=True)
    stage = models.CharField(max_length=100, help_text="e.g. Concept, MVP, Seed, Series A")
    seeking_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    website_url = models.URLField(max_length=255, blank=True)
    logo_url = models.URLField(max_length=500, blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Startup'
        verbose_name_plural = 'Startups'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} (by {self.founder.email})"
