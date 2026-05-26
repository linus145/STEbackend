import uuid
from django.db import models
from django.utils import timezone
from maincore.basemodel import SoftDeleteModel

class KPI(SoftDeleteModel):
    """
    Key Performance Indicators defined for departments or roles.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organization.Organization', 
        on_delete=models.CASCADE, 
        related_name='kpis',
        null=True,
        blank=True
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    target_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=50, blank=True)
    
    def __str__(self):
        org_name = self.organization.name if self.organization else "Global"
        return f"{self.name} - {org_name}"

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
    organization = models.ForeignKey(
        'organization.Organization', 
        on_delete=models.CASCADE, 
        related_name='goals',
        null=True,
        blank=True
    )
    employee = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE, related_name='my_goals'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    kpi = models.ForeignKey(KPI, on_delete=models.SET_NULL, null=True, blank=True)
    parent_goal = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='sub_goals')
    
    start_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    progress_percentage = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} for {self.employee}"

class PerformanceCycle(SoftDeleteModel):
    """
    Defines appraisal windows (e.g., '2026 Mid-Year Evaluation', 'Q1 2026').
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organization.Organization', 
        on_delete=models.CASCADE, 
        related_name='performance_cycles',
        null=True,
        blank=True
    )
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    due_date = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        org_name = self.organization.name if self.organization else "Global"
        return f"{self.name} - {org_name}"

class Competency(SoftDeleteModel):
    """
    Standard core competencies mapped to roles.
    """
    CATEGORY_CHOICES = (
        ('core', 'Core'),
        ('technical', 'Technical'),
        ('leadership', 'Leadership'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organization.Organization', 
        on_delete=models.CASCADE, 
        related_name='competencies',
        null=True,
        blank=True
    )
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='core')
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

class CompetencyScore(SoftDeleteModel):
    """
    Score on a 1-5 scale for a specific competency during a review.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.ForeignKey('PerformanceReview', on_delete=models.CASCADE, related_name='competency_scores')
    competency = models.ForeignKey(Competency, on_delete=models.CASCADE)
    score = models.IntegerField(help_text="1-5 rating scale", null=True, blank=True)
    weight = models.DecimalField(max_digits=4, decimal_places=2, help_text="Percentage of total competency score", default=100.0)

    def __str__(self):
        return f"{self.competency.name} Score for {self.review.employee}"

class PerformanceReview(SoftDeleteModel):
    """
    Periodic performance reviews.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organization.Organization', 
        on_delete=models.CASCADE, 
        related_name='reviews',
        null=True,
        blank=True
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
    
    cycle = models.ForeignKey(PerformanceCycle, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviews')

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'), 
        ('SELF_APPRAISAL', 'Self-Appraisal Pending'),
        ('MANAGER_REVIEW', 'Manager Review Pending'),
        ('SUBMITTED', 'Submitted'), 
        ('ACKNOWLEDGED', 'Acknowledged')
    ]
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES,
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
    FEEDBACK_TYPES = [
        ('self', 'Self Appraisal'),
        ('peer', 'Peer Review'),
        ('manager', 'Manager Review'),
        ('direct_report', 'Direct Report')
    ]
    feedback_type = models.CharField(max_length=20, choices=FEEDBACK_TYPES, default='peer')
    is_anonymous = models.BooleanField(default=False)
    content = models.TextField()
    rating = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback from {self.provider} for {self.review.employee}"

class PerformanceWeightConfiguration(SoftDeleteModel):
    """
    Configures metric weighting per startup. 
    Allows flexibility if a startup values execution (goals) over subjective feedback.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        'organization.Organization', 
        on_delete=models.CASCADE, 
        related_name='performance_weight_config',
        null=True,
        blank=True
    )
    goal_weight = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.60, 
        help_text="Weight for goal progress percentage (e.g., 0.60 for 60%)"
    )
    feedback_weight = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.40, 
        help_text="Weight for 360/manager feedback ratings (e.g., 0.40 for 40%)"
    )

    def __str__(self):
        org_name = self.organization.name if self.organization else "Global"
        return f"Weights for {org_name}"


class PerformanceScoreBreakdown(SoftDeleteModel):
    """
    Caches calculated results derived during a PerformanceReview window.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.OneToOneField(
        PerformanceReview, 
        on_delete=models.CASCADE, 
        related_name='score_breakdown'
    )
    
    # Aggregated raw components
    avg_goal_progress = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    avg_feedback_rating = models.DecimalField(max_digits=4, decimal_places=2, default=0.00)
    
    # Final mathematically calculated composite score (normalized out of 100)
    final_calculated_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    calculated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Breakdown for {self.review.employee} - Score: {self.final_calculated_score}%"
