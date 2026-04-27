from rest_framework import serializers
from django.contrib.auth import get_user_model
from startups.serializers import CompanyProfileSerializer, CompanyHRProfileSerializer
from .models import JobPost, JobApplication

User = get_user_model()


# ─── Job Posts ──────────────────────────────────────────────────────


class JobPostListSerializer(serializers.ModelSerializer):
    """Read-only serializer for public job listings with nested company info."""

    company_name = serializers.CharField(source="company.company_name", read_only=True)
    company_logo = serializers.URLField(source="company.logo_url", read_only=True)
    company_id = serializers.UUIDField(source="company.id", read_only=True)
    company_is_genuine = serializers.BooleanField(source="company.is_genuine", read_only=True)
    hr_profile = CompanyHRProfileSerializer(source="company.hr_profile", read_only=True)
    applications_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = JobPost
        fields = (
            "id",
            "company_id",
            "company_name",
            "company_logo",
            "title",
            "description",
            "location",
            "job_type",
            "work_mode",
            "salary_min",
            "salary_max",
            "currency",
            "skills_required",
            "experience_level",
            "status",
            "deadline",
            "applications_count",
            "company_is_genuine",
            "hr_profile",
            "created_at",
        )


class JobPostDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with full company info for job detail view."""

    company = CompanyProfileSerializer(read_only=True)
    applications_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = JobPost
        fields = (
            "id",
            "company",
            "title",
            "description",
            "location",
            "job_type",
            "work_mode",
            "salary_min",
            "salary_max",
            "currency",
            "skills_required",
            "experience_level",
            "status",
            "deadline",
            "applications_count",
            "created_at",
            "updated_at",
        )


class JobPostCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new job post."""

    class Meta:
        model = JobPost
        fields = (
            "title",
            "description",
            "location",
            "job_type",
            "work_mode",
            "salary_min",
            "salary_max",
            "currency",
            "skills_required",
            "experience_level",
            "status",
            "deadline",
        )

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("Job title is required.")
        return value.strip()

    def validate_description(self, value):
        if not value.strip():
            raise serializers.ValidationError("Job description is required.")
        return value.strip()

    def validate(self, data):
        salary_min = data.get("salary_min")
        salary_max = data.get("salary_max")
        if salary_min and salary_max and salary_min > salary_max:
            raise serializers.ValidationError(
                {"salary_max": "Maximum salary must be greater than minimum salary."}
            )
        return data


class JobPostUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating a job post — all fields optional."""

    class Meta:
        model = JobPost
        fields = (
            "title",
            "description",
            "location",
            "job_type",
            "work_mode",
            "salary_min",
            "salary_max",
            "currency",
            "skills_required",
            "experience_level",
            "status",
            "deadline",
        )

    def validate(self, data):
        salary_min = data.get("salary_min", getattr(self.instance, "salary_min", None))
        salary_max = data.get("salary_max", getattr(self.instance, "salary_max", None))
        if salary_min and salary_max and salary_min > salary_max:
            raise serializers.ValidationError(
                {"salary_max": "Maximum salary must be greater than minimum salary."}
            )
        return data


# ─── Job Applications ──────────────────────────────────────────────


class ApplicantMiniSerializer(serializers.ModelSerializer):
    """Minimal user info for displaying applicants to the recruiter."""

    profile_image_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "first_name", "last_name", "email", "profile_image_url")

    def get_profile_image_url(self, obj):
        if hasattr(obj, "founder_profile") and obj.founder_profile:
            return obj.founder_profile.profile_image_url
        if hasattr(obj, "investor_profile") and obj.investor_profile:
            return obj.investor_profile.profile_image_url
        return ""


class JobApplicationSerializer(serializers.ModelSerializer):
    """Read serializer for viewing applications (recruiter side)."""

    applicant = ApplicantMiniSerializer(read_only=True)
    job_title = serializers.CharField(source="job.title", read_only=True)

    class Meta:
        model = JobApplication
        fields = (
            "id",
            "job",
            "job_title",
            "applicant",
            "resume_url",
            "cover_letter",
            "status",
            "applied_at",
            "updated_at",
        )
        read_only_fields = ("id", "job", "job_title", "applicant", "applied_at", "updated_at")


class JobApplicationCreateSerializer(serializers.ModelSerializer):
    """Serializer for users applying to a job."""

    class Meta:
        model = JobApplication
        fields = ("resume_url", "cover_letter")


class JobApplicationStatusSerializer(serializers.Serializer):
    """Serializer for updating application status by recruiter."""

    status = serializers.ChoiceField(
        choices=JobApplication.STATUS_CHOICES,
        required=True,
    )
