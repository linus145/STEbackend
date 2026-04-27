from rest_framework import serializers
from .models import Startup, CompanyProfile, CompanyHRProfile


class CompanyHRProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyHRProfile
        fields = (
            "id",
            "name",
            "email",
            "phone",
            "designation",
            "profile_image_url",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class CompanyProfileSerializer(serializers.ModelSerializer):
    """Full company profile serializer for read operations."""

    owner_email = serializers.EmailField(
        source="owner.email", read_only=True, allow_null=True
    )
    owner_name = serializers.SerializerMethodField()
    total_jobs = serializers.SerializerMethodField()
    hr_profile = CompanyHRProfileSerializer(read_only=True)

    class Meta:
        model = CompanyProfile
        fields = (
            "id",
            "owner_email",
            "owner_name",
            "company_name",
            "company_email",
            "logo_url",
            "banner_url",
            "industry",
            "company_size",
            "description",
            "website",
            "founded_year",
            "location",
            "is_approved",
            "is_genuine",
            "hr_profile",
            "total_jobs",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner_email",
            "owner_name",
            "is_approved",
            "is_genuine",
            "total_jobs",
            "created_at",
            "updated_at",
        )

    def get_owner_name(self, obj):
        if obj.owner:
            return f"{obj.owner.first_name} {obj.owner.last_name}".strip()
        return "Company Account"

    def get_total_jobs(self, obj):
        return obj.job_posts.filter(is_deleted=False).count()


class CompanyRegisterSerializer(serializers.ModelSerializer):
    """Serializer for company registration — write-only fields."""

    class Meta:
        model = CompanyProfile
        fields = (
            "company_name",
            "company_email",
            "company_password",
            "logo_url",
            "banner_url",
            "industry",
            "company_size",
            "description",
            "website",
            "founded_year",
            "location",
        )
        extra_kwargs = {"company_password": {"write_only": True}}

    def create(self, validated_data):
        password = validated_data.pop("company_password", None)
        instance = super().create(validated_data)
        if password:
            instance.set_password(password)
            instance.save()
        return instance

    def validate_company_email(self, value):
        if CompanyProfile.objects.filter(company_email=value).exists():
            raise serializers.ValidationError(
                "A company with this email already exists."
            )
        return value

    def validate_company_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Company name is required.")
        return value.strip()

    def validate_industry(self, value):
        if not value.strip():
            raise serializers.ValidationError("Industry is required.")
        return value.strip()


class CompanyLoginSerializer(serializers.Serializer):
    """Serializer for company login."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class CompanyUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating company profile — all fields optional."""

    class Meta:
        model = CompanyProfile
        fields = (
            "company_name",
            "logo_url",
            "banner_url",
            "industry",
            "company_size",
            "description",
            "website",
            "founded_year",
            "location",
        )


class StartupSerializer(serializers.ModelSerializer):
    founder_email = serializers.EmailField(source="founder.email", read_only=True)
    founder_first_name = serializers.CharField(
        source="founder.first_name", read_only=True
    )

    class Meta:
        model = Startup
        fields = (
            "id",
            "founder",
            "founder_email",
            "founder_first_name",
            "name",
            "pitch",
            "industry",
            "stage",
            "seeking_amount",
            "website_url",
            "logo_url",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "founder", "created_at", "updated_at")


class StartupCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Startup
        fields = (
            "name",
            "pitch",
            "industry",
            "stage",
            "seeking_amount",
            "website_url",
            "logo_url",
        )
