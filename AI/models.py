from django.db import models
import uuid
from django.conf import settings

class AIScreeningReport(models.Model):
    """
    Stores historical AI screening results for a specific job.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_id = models.UUIDField(db_index=True)
    job_title = models.CharField(max_length=255)
    recruiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_screening_reports"
    )
    results = models.JSONField(help_text="Detailed screening results including candidate scores")
    is_deleted = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "AI Screening Report"
        verbose_name_plural = "AI Screening Reports"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report for {self.job_title} - {self.created_at.strftime('%Y-%m-%d')}"
