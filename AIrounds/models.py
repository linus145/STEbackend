from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class InterviewSession(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("ACTIVE", "Active"),
        ("EVALUATING", "Evaluating"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
        ("FAILED", "Failed"),
    ]

    STRATEGY_TIER_CHOICES = [
        ("AUTO", "AI Auto-select"),
        ("TECHNICAL", "Technical Screen"),
        ("CODING", "Live Code Assessment"),
        ("HR", "Cultural Alignment"),
        ("SYSTEM_DESIGN", "Architecture Design"),
        ("BEHAVIORAL", "Situational Analysis"),
    ]

    EVALUATION_DEPTH_CHOICES = [
        ("AUTO", "AI Recommended"),
        ("ENTRY", "Entry Level"),
        ("MID", "Mid Level"),
        ("SENIOR", "Senior Level"),
        ("LEAD", "Lead Level"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    candidate = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="interview_sessions"
    )
    application = models.ForeignKey(
        "jobs.JobApplication",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="interview_sessions",
    )
    job_title = models.CharField(max_length=255)
    job_description = models.TextField()
    resume_data = models.JSONField(null=True, blank=True)
    candidate_skills = models.JSONField(null=True, blank=True)
    candidate_experience = models.TextField(null=True, blank=True)

    # New Orchestration Fields
    config = models.JSONField(null=True, blank=True)  # Overall interview settings
    invite_token = models.UUIDField(default=uuid.uuid4, unique=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    verification_status = models.JSONField(default=dict)  # webcam, mic, identity status

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    overall_score = models.IntegerField(default=0)
    summary = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Interview for {self.candidate.email} - {self.job_title}"


class InterviewRound(models.Model):
    DESIGNATION_CHOICES = [
        ("APPLICATION_SCREENING", "Application Screening"),
        ("ATS_RESUME_SCREENING", "ATS Resume Screening"),
        ("HR_SCREENING", "HR Screening"),
        ("APTITUDE_ROUND", "Aptitude Round"),
        ("LOGICAL_REASONING", "Logical Reasoning Round"),
        ("COMMUNICATION_ROUND", "Communication Round"),
        ("TECHNICAL_SCREENING", "Technical Screening"),
        ("TECHNICAL_INTERVIEW", "Technical Interview"),
        ("CODING_ROUND", "Coding Round"),
        ("LIVE_CODING", "Live Coding Round"),
        ("MACHINE_CODING", "Machine Coding Round"),
        ("DEBUGGING_ROUND", "Debugging Round"),
        ("DATABASE_ROUND", "Database Round"),
        ("API_DESIGN", "API Design Round"),
        ("BACKEND_ROUND", "Backend Round"),
        ("FRONTEND_ROUND", "Frontend Round"),
        ("FULL_STACK_ROUND", "Full Stack Round"),
        ("DEVOPS_ROUND", "DevOps Round"),
        ("CLOUD_ROUND", "Cloud Round"),
        ("SECURITY_ROUND", "Security Round"),
        ("AI_ML_ROUND", "AI/ML Round"),
        ("SYSTEM_DESIGN", "System Design Round"),
        ("ARCHITECTURE_ROUND", "Architecture Round"),
        ("CASE_STUDY", "Case Study Round"),
        ("PRODUCT_THINKING", "Product Thinking Round"),
        ("BEHAVIORAL_ROUND", "Behavioral Round"),
        ("SITUATIONAL_ROUND", "Situational Round"),
        ("LEADERSHIP_ROUND", "Leadership Round"),
        ("TEAM_COLLABORATION", "Team Collaboration Round"),
        ("MANAGERIAL_ROUND", "Managerial Round"),
        ("CULTURAL_FIT", "Cultural Fit Round"),
        ("CLIENT_ROUND", "Client Round"),
        ("DIRECTOR_ROUND", "Director Round"),
        ("CTO_ROUND", "CTO Round"),
        ("FOUNDER_ROUND", "Founder Round"),
        ("FINAL_HR_ROUND", "Final HR Round"),
        ("SALARY_NEGOTIATION", "Salary Negotiation Round"),
        ("OFFER_DISCUSSION", "Offer Discussion Round"),
        ("BGV_ROUND", "Background Verification Round"),
        ("PRE_ONBOARDING", "Pre-Onboarding Round"),
    ]

    QUESTION_FORMAT_CHOICES = [
        ("AUTO", "AI Recommended"),
        ("TEXT", "Text / Typing Answer"),
        ("MCQ", "Multiple Choice (Single Answer)"),
        ("MULTI_SELECT", "Multiple Choice (Multiple Answers)"),
        ("CODE", "Code / Programming"),
        ("VIDEO", "AI Voice/Video Interview"),
    ]

    PROGRAMMING_LANGUAGE_CHOICES = [
        ("", "None (Not Applicable)"),
        ("PYTHON", "Python"),
        ("JAVASCRIPT", "JavaScript"),
        ("TYPESCRIPT", "TypeScript"),
        ("JAVA", "Java"),
        ("CSHARP", "C#"),
        ("CPP", "C++"),
        ("C", "C"),
        ("GO", "Go"),
        ("RUST", "Rust"),
        ("RUBY", "Ruby"),
        ("PHP", "PHP"),
        ("SWIFT", "Swift"),
        ("KOTLIN", "Kotlin"),
        ("DART", "Dart"),
        ("R", "R"),
        ("SQL", "SQL"),
        ("SHELL", "Shell / Bash"),
    ]

    ROUND_CATEGORY_CHOICES = [
        ("NON_CODING", "Non-Coding"),
        ("CODING", "Coding"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        InterviewSession, on_delete=models.CASCADE, related_name="rounds"
    )

    # Round Category (Coding vs Non-Coding)
    round_category = models.CharField(
        max_length=20,
        choices=ROUND_CATEGORY_CHOICES,
        default="NON_CODING",
    )

    # Strategy Tier (Category) — legacy, auto-managed
    strategy_tier = models.CharField(
        max_length=50,
        choices=InterviewSession.STRATEGY_TIER_CHOICES,
        default="TECHNICAL",
    )

    # Designation (Specific Name)
    designation = models.CharField(
        max_length=100, choices=DESIGNATION_CHOICES, default="TECHNICAL_SCREENING"
    )

    # Evaluation Depth
    difficulty = models.CharField(
        max_length=20, choices=InterviewSession.EVALUATION_DEPTH_CHOICES, default="MID"
    )

    # Question Format
    question_format = models.CharField(
        max_length=20, choices=QUESTION_FORMAT_CHOICES, default="TEXT"
    )

    # Programming Language (optional, for CODE rounds)
    programming_language = models.CharField(
        max_length=20, choices=PROGRAMMING_LANGUAGE_CHOICES, default="", blank=True
    )

    # Keep round_type for backward compatibility or as a display string
    round_type = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, default="ACTIVE")

    # New Orchestration Fields
    timer_seconds = models.IntegerField(default=0)  # 0 means no limit
    max_questions = models.IntegerField(default=10)
    settings = models.JSONField(default=dict)  # Round-specific settings
    total_marks = models.IntegerField(default=0)

    round_score = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.designation} - {self.session.id}"


class InterviewQuestion(models.Model):
    QUESTION_TYPE_CHOICES = [
        ("TEXT", "Text / Typing"),
        ("MCQ", "Multiple Choice (Single)"),
        ("MULTI_SELECT", "Multiple Select"),
        ("CODE", "Code / Programming"),
        ("VIDEO", "AI Voice/Video Interview"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    round = models.ForeignKey(
        InterviewRound, on_delete=models.CASCADE, related_name="questions"
    )
    question_text = models.TextField()
    question_type = models.CharField(
        max_length=20, choices=QUESTION_TYPE_CHOICES, default="TEXT"
    )
    mcq_options = models.JSONField(
        null=True, blank=True
    )  # [{"label": "A", "text": "...", "is_correct": true}]
    ideal_answer = models.TextField(
        null=True, blank=True
    )  # AI-generated ideal answer or evaluation criteria
    expected_topics = models.JSONField(null=True, blank=True)
    marks = models.IntegerField(default=10)
    candidate_answer = models.TextField(null=True, blank=True)
    evaluation = models.JSONField(null=True, blank=True)
    asked_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Q for {self.round.designation} - {self.id}"


class CandidateInterviewLink(models.Model):
    """Active link for candidates to take their AI interview."""

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("STARTED", "Started"),
        ("COMPLETED", "Completed"),
        ("EXPIRED", "Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        InterviewSession, on_delete=models.CASCADE, related_name="active_link"
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)

    # Exam credentials (NOT Django auth — standalone exam access)
    exam_username = models.CharField(
        max_length=100, unique=True, db_index=True, default="", blank=True
    )
    exam_password = models.CharField(max_length=50, default="", blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")
    expires_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Link for {self.session.candidate.email} - {self.status}"

    def save(self, *args, **kwargs):
        if not self.exam_username:
            self.exam_username, self.exam_password = self._generate_credentials()
        super().save(*args, **kwargs)

    def _generate_credentials(self):
        import random
        import string

        candidate = self.session.candidate
        first = (
            candidate.first_name.lower().replace(" ", "")
            if candidate.first_name
            else "candidate"
        )
        pin = "".join(random.choices(string.digits, k=4))
        username = f"{first}.exam.{pin}"
        password = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        return username, password

    @property
    def is_valid(self):
        from django.utils import timezone

        if self.status in ("COMPLETED", "EXPIRED"):
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            self.status = "EXPIRED"
            self.save(update_fields=["status"])
            return False
        return True
