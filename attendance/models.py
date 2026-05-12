import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from maincore.basemodel import SoftDeleteModel

class Shift(SoftDeleteModel):
    """
    Work shifts defined for a startup.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='shifts'
    )
    name = models.CharField(max_length=255)
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_duration = models.IntegerField(default=60, help_text="Break duration in minutes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.start_time} - {self.end_time})"

class Attendance(SoftDeleteModel):
    """
    Daily attendance record for an employee.
    """
    STATUS_CHOICES = (
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('LATE', 'Late'),
        ('HALF_DAY', 'Half Day'),
        ('ON_LEAVE', 'On Leave'),
        ('WEEKEND', 'Weekend'),
        ('HOLIDAY', 'Holiday'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='attendance_records'
    )
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='attendance_history'
    )
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PRESENT')
    
    # Calculated fields
    total_work_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    is_late = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('employee', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.employee} - {self.date}"

class WorkSession(models.Model):
    """
    Multiple check-in/check-out sessions within a single day.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attendance = models.ForeignKey(
        Attendance, on_delete=models.CASCADE, related_name='sessions'
    )
    check_in = models.DateTimeField(default=timezone.now)
    check_out = models.DateTimeField(null=True, blank=True)
    location_in = models.CharField(max_length=255, blank=True)
    location_out = models.CharField(max_length=255, blank=True)
    
    def __str__(self):
        return f"Session for {self.attendance}"
