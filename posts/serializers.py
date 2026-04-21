from rest_framework import serializers
from .models import Post

class PostSerializer(serializers.ModelSerializer):
    author_id = serializers.UUIDField(source='author.id', read_only=True)
    author_email = serializers.EmailField(source='author.email', read_only=True)
    author_first_name = serializers.CharField(source='author.first_name', read_only=True)
    author_role = serializers.CharField(source='author.role', read_only=True)
    author_image_url = serializers.SerializerMethodField()
    author_linkedin_url = serializers.SerializerMethodField()
    
    # These will be dynamically injected via queryset annotations in the service layer
    likes_count = serializers.IntegerField(read_only=True, default=0)
    comments_count = serializers.IntegerField(read_only=True, default=0)
    user_has_liked = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Post
        fields = (
            'id', 'author_id', 'author_email', 'author_first_name', 'author_role', 
            'author_image_url', 'author_linkedin_url',
            'content', 'media_url', 'likes_count', 'comments_count', 
            'user_has_liked', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_author_image_url(self, obj):
        user = obj.author
        if hasattr(user, 'founder_profile') and user.founder_profile.profile_image_url:
            return user.founder_profile.profile_image_url
        if hasattr(user, 'investor_profile') and user.investor_profile.profile_image_url:
            return user.investor_profile.profile_image_url
        return None

    def get_author_linkedin_url(self, obj):
        user = obj.author
        if hasattr(user, 'founder_profile') and user.founder_profile.linkedin_url:
            return user.founder_profile.linkedin_url
        if hasattr(user, 'investor_profile') and user.investor_profile.linkedin_url:
            return user.investor_profile.linkedin_url
        return None

class PostCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ('content', 'media_url')

    def validate_content(self, value):
        if len(value) > 1800:
            raise serializers.ValidationError("System constraints allow a maximum of 1800 characters per signal stream.")
        return value
