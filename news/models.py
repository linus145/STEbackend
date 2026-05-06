import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from maincore.basemodel import SoftDeleteModel

class News(SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='news_articles',
        db_index=True
    )
    title = models.CharField(max_length=255)
    short_title = models.CharField(max_length=100, blank=True, null=True)
    content = models.TextField()
    media_url = models.URLField(max_length=500, blank=True, null=True)
    
    # News Categories/Tags (Managed in Admin)
    is_popular = models.BooleanField(default=False, db_index=True)
    is_trending = models.BooleanField(default=False, db_index=True)
    is_top_news = models.BooleanField(default=False, db_index=True)
    
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'News Article'
        verbose_name_plural = 'News Articles'
        ordering = ['-created_at']

    def __str__(self):
        return self.title
