from django.db import models
import uuid

class AgentExecution(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_type = models.CharField(max_length=50, default='browser_agent')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    execution_time = models.FloatField(null=True, blank=True)
    screenshot = models.ImageField(upload_to='agent_screenshots/', null=True, blank=True)
    actions_performed = models.JSONField(default=list)
    metadata = models.JSONField(default=dict)

    def __str__(self):
        return f"{self.agent_type} - {self.status} ({self.id})"

class AgentLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(AgentExecution, related_name='logs', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10, default='INFO')
    message = models.TextField()
    action = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"[{self.level}] {self.message[:50]}"
