from django.db import models

class AgentSettings(models.Model):
    organization = models.ForeignKey('organization.Organization', on_delete=models.CASCADE, null=True, blank=True)
    startup = models.ForeignKey('startups.Startup', on_delete=models.CASCADE, null=True, blank=True)
    llm_model = models.CharField(max_length=100, default='gemini-2.5-flash')
    max_iterations = models.IntegerField(default=30)
    system_prompt = models.TextField(default='', blank=True)
    autonomy_level = models.CharField(max_length=50, default='full_autonomy')

    def __str__(self):
        return f"Agent Settings for {self.organization or self.startup}"

class AgentScheduling(models.Model):
    organization = models.ForeignKey('organization.Organization', on_delete=models.CASCADE, null=True, blank=True)
    startup = models.ForeignKey('startups.Startup', on_delete=models.CASCADE, null=True, blank=True)
    enabled = models.BooleanField(default=False)
    recurrence = models.CharField(max_length=50, default='daily') # daily, weekly, monthly, yearly
    execution_time = models.TimeField(default='09:00:00')
    task_type = models.CharField(max_length=500, default='payroll_runs')
    notification_email = models.EmailField(default='', blank=True)
    last_executed_at = models.DateTimeField(null=True, blank=True)
    day_of_week = models.CharField(max_length=20, null=True, blank=True, default='Monday')
    day_of_month = models.IntegerField(null=True, blank=True, default=1)
    month_of_year = models.IntegerField(null=True, blank=True, default=1)
    command = models.TextField(default='Execute default task audit and sync pipeline', blank=True)
    max_executions = models.IntegerField(default=5)
    run_count = models.IntegerField(default=0)

    def __str__(self):
        return f"Agent Scheduling for {self.organization or self.startup}"

class AgentSchedulingLog(models.Model):
    schedule = models.ForeignKey('AgentScheduling', on_delete=models.CASCADE, null=True, blank=True, related_name='logs')
    task_type = models.CharField(max_length=200, default='payroll_runs')
    command = models.TextField(default='', blank=True)
    status = models.CharField(max_length=50, default='running') # running, success, failed
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration = models.FloatField(default=0.0) # in seconds
    actions_performed = models.JSONField(default=list, blank=True) # list of actions performed
    error_message = models.TextField(default='', blank=True)

    def __str__(self):
        return f"Scheduling Log {self.id} - {self.task_type} ({self.status})"
