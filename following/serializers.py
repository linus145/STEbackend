from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Follow, CompanyFollow

User = get_user_model()


class FollowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Follow
        fields = ("id", "follower", "following", "created_at")
        read_only_fields = ("id", "follower", "created_at")


class FollowUserSerializer(serializers.ModelSerializer):
    """Lightweight user serializer for follower/following lists."""
    headline = serializers.SerializerMethodField()
    profile_image_url = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "email", "first_name", "last_name", "role",
            "headline", "profile_image_url", "is_following",
        )

    def get_headline(self, obj):
        for attr in ("founder_profile", "investor_profile", "mentor_profile"):
            profile = getattr(obj, attr, None)
            if profile and getattr(profile, "headline", None):
                return profile.headline
        return obj.role.capitalize() if obj.role else "Member"

    def get_profile_image_url(self, obj):
        for attr in ("founder_profile", "investor_profile", "mentor_profile"):
            profile = getattr(obj, attr, None)
            if profile and getattr(profile, "profile_image_url", None):
                return profile.profile_image_url
        return None

    def get_is_following(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return Follow.objects.filter(follower=request.user, following=obj).exists()


class CompanyFollowSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.company_name", read_only=True)
    logo_url = serializers.URLField(source="company.logo_url", read_only=True)
    banner_url = serializers.URLField(source="company.banner_url", read_only=True)
    industry = serializers.CharField(source="company.industry", read_only=True)
    website = serializers.URLField(source="company.website", read_only=True)
    description = serializers.CharField(source="company.description", read_only=True)
    location = serializers.CharField(source="company.location", read_only=True)
    company_size = serializers.CharField(source="company.company_size", read_only=True)
    founded_year = serializers.IntegerField(source="company.founded_year", read_only=True)

    class Meta:
        model = CompanyFollow
        fields = (
            "id", "follower", "company", "company_name", "logo_url",
            "banner_url", "industry", "website", "description",
            "location", "company_size", "founded_year", "created_at"
        )
        read_only_fields = ("id", "follower", "created_at")


class FollowCountsSerializer(serializers.Serializer):
    followers_count = serializers.IntegerField()
    following_count = serializers.IntegerField()
    is_following = serializers.BooleanField(default=False)


class CompanyFollowCountsSerializer(serializers.Serializer):
    followers_count = serializers.IntegerField()
    is_following = serializers.BooleanField(default=False)
