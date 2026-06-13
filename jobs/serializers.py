from rest_framework import serializers
from django.contrib.auth import get_user_model
from startups.serializers import CompanyProfileSerializer, CompanyHRProfileSerializer
from startups.models import CompanyHRProfile
from jobs.models import JobPost, JobApplication, Skill, TalentPipeline, SavedJob


class SkillSerializer(serializers.ModelSerializer):
    """Serializer for the Skill model."""
    class Meta:
        model = Skill
        fields = ("id", "name", "category")

User = get_user_model()


# ─── Job Posts ──────────────────────────────────────────────────────


class JobPostListSerializer(serializers.ModelSerializer):
    """Read-only serializer for public job listings with nested company info."""

    company_name = serializers.CharField(source="company.company_name", read_only=True)
    company_logo = serializers.URLField(source="company.logo_url", read_only=True)
    company_id = serializers.UUIDField(source="company.id", read_only=True)
    company_is_genuine = serializers.BooleanField(source="company.is_genuine", read_only=True)
    owner_user_id = serializers.UUIDField(source="company.owner_id", read_only=True)
    hr_profile = serializers.SerializerMethodField()
    applications_count = serializers.IntegerField(read_only=True)
    skills = SkillSerializer(many=True, read_only=True)

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
            "job_category",
            "work_mode",
            "salary_min",
            "salary_max",
            "currency",
            "skills",
            "skills_required",
            "experience_level",
            "open_positions",
            "department",
            "status",
            "hiring_status",
            "deadline",
            "applications_count",
            "company_is_genuine",
            "owner_user_id",
            "hr_profile",
            "is_ai_generated",
            "created_at",
        )

    def get_hr_profile(self, obj):
        if obj.hr_profile and not obj.hr_profile.is_deleted:
            return CompanyHRProfileSerializer(obj.hr_profile).data
        fallback = obj.company.hr_profiles.filter(is_deleted=False).first()
        if fallback:
            return CompanyHRProfileSerializer(fallback).data
        return None


class JobPostDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with full company info for job detail view."""

    company = CompanyProfileSerializer(read_only=True)
    applications_count = serializers.IntegerField(read_only=True)
    skills = SkillSerializer(many=True, read_only=True)
    hr_profile = serializers.SerializerMethodField()

    class Meta:
        model = JobPost
        fields = (
            "id",
            "company",
            "title",
            "description",
            "location",
            "job_type",
            "job_category",
            "work_mode",
            "salary_min",
            "salary_max",
            "currency",
            "skills",
            "skills_required",
            "experience_level",
            "open_positions",
            "department",
            "status",
            "hiring_status",
            "deadline",
            "applications_count",
            "hr_profile",
            "is_ai_generated",
            "created_at",
            "updated_at",
        )

    def get_hr_profile(self, obj):
        if obj.hr_profile and not obj.hr_profile.is_deleted:
            return CompanyHRProfileSerializer(obj.hr_profile).data
        fallback = obj.company.hr_profiles.filter(is_deleted=False).first()
        if fallback:
            return CompanyHRProfileSerializer(fallback).data
        return None


class JobPostCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new job post."""
    skills = serializers.PrimaryKeyRelatedField(many=True, queryset=Skill.objects.all(), required=False)
    hr_profile = serializers.PrimaryKeyRelatedField(queryset=CompanyHRProfile.objects.all(), required=False, allow_null=True)

    class Meta:
        model = JobPost
        fields = (
            "title",
            "description",
            "location",
            "job_type",
            "job_category",
            "work_mode",
            "salary_min",
            "salary_max",
            "currency",
            "skills",
            "skills_required",
            "experience_level",
            "open_positions",
            "department",
            "status",
            "hiring_status",
            "hr_profile",
            "deadline",
        )

    def validate_hr_profile(self, value):
        if value:
            request = self.context.get("request")
            if request and hasattr(request.user, "company_profile"):
                if value.company != request.user.company_profile:
                    raise serializers.ValidationError("HR profile does not belong to your company.")
        return value

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
    skills = serializers.PrimaryKeyRelatedField(many=True, queryset=Skill.objects.all(), required=False)
    hr_profile = serializers.PrimaryKeyRelatedField(queryset=CompanyHRProfile.objects.all(), required=False, allow_null=True)

    class Meta:
        model = JobPost
        fields = (
            "title",
            "description",
            "location",
            "job_type",
            "job_category",
            "work_mode",
            "salary_min",
            "salary_max",
            "currency",
            "skills",
            "skills_required",
            "experience_level",
            "open_positions",
            "department",
            "status",
            "hiring_status",
            "hr_profile",
            "deadline",
        )

    def validate_hr_profile(self, value):
        if value:
            request = self.context.get("request")
            if request and hasattr(request.user, "company_profile"):
                if value.company != request.user.company_profile:
                    raise serializers.ValidationError("HR profile does not belong to your company.")
        return value

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
    headline = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "first_name", "last_name", "email", "profile_image_url", "headline")

    def get_profile_image_url(self, obj):
        if hasattr(obj, "founder_profile") and obj.founder_profile:
            return obj.founder_profile.profile_image_url
        if hasattr(obj, "mentor_profile") and obj.mentor_profile:
            return obj.mentor_profile.profile_image_url
        return ""

    def get_headline(self, obj):
        if hasattr(obj, 'founder_profile') and obj.founder_profile.headline:
            return obj.founder_profile.headline
        if hasattr(obj, 'investor_profile') and obj.investor_profile.headline:
            return obj.investor_profile.headline
        if hasattr(obj, 'mentor_profile') and obj.mentor_profile.headline:
            return obj.mentor_profile.headline
        return obj.role.capitalize() if obj.role else "Member"


class JobApplicationSerializer(serializers.ModelSerializer):
    """Read serializer for viewing applications (recruiter side)."""

    applicant = ApplicantMiniSerializer(read_only=True)
    job_title = serializers.CharField(source="job.title", read_only=True)
    is_synced = serializers.SerializerMethodField()

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
            "ai_score",
            "ai_analysis",
            "applied_at",
            "updated_at",
            "is_synced",
        )
        read_only_fields = ("id", "job", "job_title", "applicant", "ai_score", "ai_analysis", "applied_at", "updated_at", "is_synced")

    def get_is_synced(self, obj):
        return hasattr(obj, 'interview_candidate')



class JobApplicationCreateSerializer(serializers.ModelSerializer):
    """Serializer for users applying to a job."""

    class Meta:
        model = JobApplication
        fields = ("resume_url", "cover_letter")
        extra_kwargs = {
            'resume_url': {'required': False, 'allow_blank': True}
        }


class JobApplicationStatusSerializer(serializers.ModelSerializer):
    """Serializer for updating application status by recruiter."""

    class Meta:
        model = JobApplication
        fields = ("status", "employment_type")


class TalentPipelineSerializer(serializers.ModelSerializer):
    """Serializer for Talent Pipeline entries."""

    talent = ApplicantMiniSerializer(read_only=True)

    class Meta:
        model = TalentPipeline
        fields = ("id", "talent", "added_at", "status", "notes")
        read_only_fields = ("id", "added_at")


class SavedJobSerializer(serializers.ModelSerializer):
    """Serializer for the SavedJob model."""
    job = JobPostListSerializer(read_only=True)

    class Meta:
        model = SavedJob
        fields = ("id", "job", "created_at")
        read_only_fields = ("id", "job", "created_at")
