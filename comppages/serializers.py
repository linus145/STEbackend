from rest_framework import serializers
from django.utils.text import slugify
from startups.models import CompanyProfile
from following.models import CompanyFollow
from jobs.models import JobPost
from .models import CompanyPage, CompanyPost


class CompanyPageJobSerializer(serializers.ModelSerializer):
    skills = serializers.SerializerMethodField()

    class Meta:
        model = JobPost
        fields = [
            "id",
            "title",
            "description",
            "location",
            "job_type",
            "work_mode",
            "salary_min",
            "salary_max",
            "currency",
            "experience_level",
            "open_positions",
            "department",
            "status",
            "hiring_status",
            "job_category",
            "skills",
            "created_at",
        ]

    def get_skills(self, obj):
        return [skill.name for skill in obj.skills.all()]


class CompanyPagePostSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_email = serializers.SerializerMethodField()
    author_avatar = serializers.SerializerMethodField()

    class Meta:
        model = CompanyPost
        fields = [
            "id",
            "content",
            "media_url",
            "is_promoted",
            "created_at",
            "author_name",
            "author_email",
            "author_avatar",
        ]

    def get_author_name(self, obj):
        if not obj.author:
            return "Anonymous"
        first = getattr(obj.author, "first_name", "") or ""
        last = getattr(obj.author, "last_name", "") or ""
        full_name = f"{first} {last}".strip()
        return full_name or obj.author.email

    def get_author_email(self, obj):
        return obj.author.email if obj.author else ""

    def get_author_avatar(self, obj):
        if not obj.author:
            return None
        if hasattr(obj.author, "founder_profile") and obj.author.founder_profile:
            return getattr(obj.author.founder_profile, "profile_image_url", None)
        return None


class CompanyPageDetailSerializer(serializers.ModelSerializer):
    # From CompanyProfile
    company_id = serializers.UUIDField(source="company.id", read_only=True)
    company_name = serializers.CharField(source="company.company_name", read_only=True)
    company_email = serializers.EmailField(source="company.company_email", read_only=True)
    industry = serializers.CharField(source="company.industry", read_only=True)
    company_size = serializers.CharField(source="company.company_size", read_only=True)
    description = serializers.CharField(source="company.description", read_only=True)
    website = serializers.URLField(source="company.website", read_only=True)
    founded_year = serializers.IntegerField(source="company.founded_year", read_only=True)
    location = serializers.CharField(source="company.location", read_only=True)
    phone = serializers.CharField(source="company.phone", read_only=True)
    
    # Visuals with fallback
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()

    # Dynamic metrics & status
    followers_count = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    active_jobs_count = serializers.SerializerMethodField()
    jobs = serializers.SerializerMethodField()
    posts = serializers.SerializerMethodField()

    class Meta:
        model = CompanyPage
        fields = [
            "id",
            "company_id",
            "slug",
            "company_name",
            "company_email",
            "tagline",
            "page_type",
            "industry",
            "company_size",
            "description",
            "overview",
            "website",
            "founded_year",
            "location",
            "phone",
            "specialties",
            "logo_url",
            "banner_url",
            "custom_logo_url",
            "custom_banner_url",
            "is_verified",
            "call_to_action_label",
            "call_to_action_url",
            "followers_count",
            "is_following",
            "is_owner",
            "active_jobs_count",
            "jobs",
            "posts",
            "created_at",
            "updated_at",
        ]

    def get_logo_url(self, obj):
        return obj.custom_logo_url or obj.company.logo_url or ""

    def get_banner_url(self, obj):
        return obj.custom_banner_url or obj.company.banner_url or ""

    def get_followers_count(self, obj):
        return CompanyFollow.objects.filter(company=obj.company).count()

    def get_is_following(self, obj):
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            return CompanyFollow.objects.filter(follower=request.user, company=obj.company).exists()
        return False

    def get_is_owner(self, obj):
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            return obj.company.owner_id == request.user.id
        return False

    def get_active_jobs_count(self, obj):
        return JobPost.objects.filter(company=obj.company, status="ACTIVE").count()

    def get_jobs(self, obj):
        jobs_qs = JobPost.objects.filter(company=obj.company, status="ACTIVE")[:6]
        return CompanyPageJobSerializer(jobs_qs, many=True).data

    def get_posts(self, obj):
        posts_qs = CompanyPost.objects.filter(company_page=obj).order_by("-created_at")[:6]
        return CompanyPagePostSerializer(posts_qs, many=True).data


class CompanyPageCreateSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=255)
    slug = serializers.CharField(max_length=255, required=False, allow_blank=True)
    tagline = serializers.CharField(max_length=300, required=False, allow_blank=True)
    page_type = serializers.ChoiceField(choices=CompanyPage.PAGE_TYPE_CHOICES, default="COMPANY")
    industry = serializers.CharField(max_length=150)
    company_size = serializers.ChoiceField(choices=CompanyProfile.COMPANY_SIZE_CHOICES, default="1-10")
    website = serializers.URLField(required=False, allow_blank=True)
    location = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    founded_year = serializers.IntegerField(required=False, allow_null=True)
    specialties = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    logo_url = serializers.URLField(required=False, allow_blank=True)
    banner_url = serializers.URLField(required=False, allow_blank=True)
    call_to_action_label = serializers.CharField(max_length=50, required=False, default="Visit website")
    call_to_action_url = serializers.URLField(required=False, allow_blank=True)

    def validate_slug(self, value):
        if value:
            clean_slug = slugify(value)
            if not clean_slug:
                raise serializers.ValidationError("Please provide a valid URL slug.")
            return clean_slug
        return value
