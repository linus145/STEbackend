import uuid
from django.db import models
from django.utils import timezone
from maincore.basemodel import SoftDeleteModel

class KPI(SoftDeleteModel):
    """
    Key Performance Indicators defined for departments or roles.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='kpis'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    target_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=50, blank=True)
    
    def __str__(self):
        return f"{self.name} - {self.startup.name}"

class Goal(SoftDeleteModel):
    """
    Specific goals assigned to employees.
    """
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='goals'
    )
    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='my_goals'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    kpi = models.ForeignKey(KPI, on_delete=models.SET_NULL, null=True, blank=True)
    
    start_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    progress_percentage = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} for {self.employee}"

class PerformanceReview(SoftDeleteModel):
    """
    Periodic performance reviews.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.Startup', 
        on_delete=models.CASCADE, 
        related_name='reviews'
    )
    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='reviews'
    )
    reviewer = models.ForeignKey(
        'employees.Employee', on_delete=models.SET_NULL, null=True, related_name='given_reviews'
    )
    review_period_start = models.DateField()
    review_period_end = models.DateField()
    
    rating = models.IntegerField(help_text="Rating from 1 to 5", null=True, blank=True)
    summary = models.TextField(blank=True)
    strengths = models.TextField(blank=True)
    areas_of_improvement = models.TextField(blank=True)
    
    status = models.CharField(
        max_length=20, 
        choices=[('DRAFT', 'Draft'), ('SUBMITTED', 'Submitted'), ('ACKNOWLEDGED', 'Acknowledged')],
        default='DRAFT'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Review for {self.employee} ({self.review_period_start} - {self.review_period_end})"

class EmployeeFeedback(SoftDeleteModel):
    """
    Feedback given to/by employees (360-degree feedback).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey(
        PerformanceReview, on_delete=models.CASCADE, related_name='feedbacks'
    )
    provider = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='feedbacks_provided'
    )
    content = models.TextField()
    rating = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback from {self.provider} for {self.review.employee}"
