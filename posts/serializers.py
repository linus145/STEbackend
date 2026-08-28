from rest_framework import serializers
from .models import Post

class PostSerializer(serializers.ModelSerializer):
    author_id = serializers.UUIDField(source='author.id', read_only=True)
    author_email = serializers.EmailField(source='author.email', read_only=True)
    author_first_name = serializers.SerializerMethodField()
    author_role = serializers.CharField(source='author.role', read_only=True)
    author_headline = serializers.SerializerMethodField()
    author_image_url = serializers.SerializerMethodField()
    author_linkedin_url = serializers.SerializerMethodField()
    
    # Company post attributes
    company_slug = serializers.SerializerMethodField()
    is_company_post = serializers.SerializerMethodField()
    
    # These will be dynamically injected via queryset annotations in the service layer
    likes_count = serializers.IntegerField(read_only=True, default=0)
    comments_count = serializers.IntegerField(read_only=True, default=0)
    user_has_liked = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Post
        fields = (
            'id', 'author_id', 'author_email', 'author_first_name', 'author_role', 
            'author_headline', 'author_image_url', 'author_linkedin_url',
            'company_slug', 'is_company_post', 'is_promoted',
            'content', 'media_url', 'visibility', 'likes_count', 'comments_count', 
            'user_has_liked', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_is_company_post(self, obj):
        return bool(obj.company_page_id)

    def get_company_slug(self, obj):
        if obj.company_page:
            return obj.company_page.slug
        return None

    def get_author_first_name(self, obj):
        if obj.company_page and hasattr(obj.company_page, 'company'):
            return obj.company_page.company.company_name
        first = getattr(obj.author, 'first_name', '') or ''
        last = getattr(obj.author, 'last_name', '') or ''
        full_name = f"{first} {last}".strip()
        return full_name or obj.author.email

    def get_author_headline(self, obj):
        if obj.company_page:
            industry = getattr(obj.company_page.company, 'industry', '') if hasattr(obj.company_page, 'company') else ''
            return obj.company_page.tagline or industry or "Company"
        user = obj.author
        if hasattr(user, 'founder_profile') and user.founder_profile.headline:
            return user.founder_profile.headline
        if hasattr(user, 'investor_profile') and user.investor_profile.headline:
            return user.investor_profile.headline
        if hasattr(user, 'mentor_profile') and user.mentor_profile.headline:
            return user.mentor_profile.headline
        return user.role.capitalize() if user.role else "Member"

    def get_author_image_url(self, obj):
        if obj.company_page:
            logo = getattr(obj.company_page.company, 'logo_url', None) if hasattr(obj.company_page, 'company') else None
            return obj.company_page.custom_logo_url or logo or None
        user = obj.author
        if hasattr(user, 'founder_profile') and user.founder_profile.profile_image_url:
            return user.founder_profile.profile_image_url
        if hasattr(user, 'investor_profile') and user.investor_profile.profile_image_url:
            return user.investor_profile.profile_image_url
        return None

    def get_author_linkedin_url(self, obj):
        if obj.company_page and hasattr(obj.company_page, 'company'):
            return getattr(obj.company_page.company, 'website', None) or None
        user = obj.author
        if hasattr(user, 'founder_profile') and user.founder_profile.linkedin_url:
            return user.founder_profile.linkedin_url
        if hasattr(user, 'investor_profile') and user.investor_profile.linkedin_url:
            return user.investor_profile.linkedin_url
        return None

class PostCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ('content', 'media_url', 'visibility')

    def validate_content(self, value):
        if len(value) > 1800:
            raise serializers.ValidationError("System constraints allow a maximum of 1800 characters per signal stream.")
        return value
