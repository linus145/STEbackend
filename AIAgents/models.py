from django.db import models
from django.contrib.auth import get_user_model
import uuid

from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class AISearchHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ai_search_history")
    query = models.TextField()
    reasoning = models.TextField(blank=True, null=True)
    count = models.IntegerField(default=0)
    candidates_data = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
