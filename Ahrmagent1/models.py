from django.db import models
import uuid
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class AgentGoal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey('organization.Organization', on_delete=models.CASCADE, null=True, blank=True, related_name='agent_goals')
    startup = models.ForeignKey('startups.Startup', on_delete=models.CASCADE, null=True, blank=True, related_name='agent_goals')
    goal = models.TextField()
    goal_type = models.CharField(max_length=100, default='autonomous')
    status = models.CharField(max_length=50, default='pending') # pending, running, completed, failed, cancelled
    priority = models.CharField(max_length=20, default='medium')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Goal: {self.goal[:50]} ({self.status})"

class AgentExecution(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    goal = models.ForeignKey(AgentGoal, on_delete=models.CASCADE, null=True, blank=True, related_name='executions')
    organization = models.ForeignKey('organization.Organization', on_delete=models.CASCADE, null=True, blank=True, related_name='agent_executions')
    startup = models.ForeignKey('startups.Startup', on_delete=models.CASCADE, null=True, blank=True, related_name='agent_executions')
    agent_type = models.CharField(max_length=50, default='browser_agent')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    execution_version = models.IntegerField(default=1)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    execution_time = models.FloatField(null=True, blank=True)
    screenshot = models.ImageField(upload_to='agent_screenshots/', null=True, blank=True)
    actions_performed = models.JSONField(default=list)
    metadata = models.JSONField(default=dict)

    def __str__(self):
        return f"{self.agent_type} - {self.status} ({self.id})"

class AgentMemory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(AgentExecution, on_delete=models.CASCADE, related_name='memories')
    memory_type = models.CharField(max_length=50) # short_term, long_term, execution, audit
    memory_key = models.CharField(max_length=255)
    memory_value = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.memory_type} - {self.memory_key} ({self.execution.id})"

class AgentDecision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(AgentExecution, on_delete=models.CASCADE, related_name='decisions')
    decision_type = models.CharField(max_length=100)
    decision_data = models.JSONField(default=dict)
    reasoning_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Decision {self.decision_type} ({self.id})"

class AgentAction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(AgentExecution, on_delete=models.CASCADE, related_name='agent_actions')
    action_type = models.CharField(max_length=100)
    action_payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Action {self.action_type} ({self.id})"

class AgentLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(AgentExecution, related_name='logs', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10, default='INFO')
    log_level = models.CharField(max_length=20, default='INFO') # Compatibility field
    message = models.TextField()
    action = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now) # Compatibility field

    def __str__(self):
        return f"[{self.level}] {self.message[:50]}"

class AgentSchedule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    goal = models.ForeignKey(AgentGoal, on_delete=models.CASCADE, related_name='schedules')
    organization = models.ForeignKey('organization.Organization', on_delete=models.CASCADE, null=True, blank=True, related_name='agent_schedules')
    startup = models.ForeignKey('startups.Startup', on_delete=models.CASCADE, null=True, blank=True, related_name='agent_schedules')
    schedule_type = models.CharField(max_length=50) # cron, interval, daily, weekly, monthly
    schedule_expression = models.CharField(max_length=100)
    next_run = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=50, default='active')

    def __str__(self):
        return f"Schedule {self.schedule_type} ({self.status})"

class AgentCheckpoint(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution = models.ForeignKey(AgentExecution, on_delete=models.CASCADE, related_name='checkpoints')
    checkpoint_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Checkpoint for {self.execution_id}"

class AgentChatHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    sender = models.CharField(max_length=10, choices=[('user', 'User'), ('bot', 'Bot')])
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    conversation_id = models.UUIDField(null=True, blank=True)

    def __str__(self):
        return f"{self.sender}: {self.text[:50]}"
