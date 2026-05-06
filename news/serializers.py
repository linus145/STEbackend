from rest_framework import serializers
from .models import News

class NewsSerializer(serializers.ModelSerializer):
    author_id = serializers.UUIDField(source='author.id', read_only=True)
    author_email = serializers.EmailField(source='author.email', read_only=True)
    author_first_name = serializers.CharField(source='author.first_name', read_only=True)
    author_last_name = serializers.CharField(source='author.last_name', read_only=True)
    author_image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = News
        fields = (
            'id', 'author_id', 'author_email', 'author_first_name', 'author_last_name',
            'author_image_url', 'title', 'short_title', 'content', 'media_url', 
            'is_popular', 'is_trending', 'is_top_news', 
            'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_author_image_url(self, obj):
        user = obj.author
        if hasattr(user, 'founder_profile') and user.founder_profile.profile_image_url:
            return user.founder_profile.profile_image_url
        if hasattr(user, 'investor_profile') and user.investor_profile.profile_image_url:
            return user.investor_profile.profile_image_url
        return None

class NewsCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = News
        fields = ('title', 'short_title', 'content', 'media_url')

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("Headline is required for news articles.")
        return value.strip()
