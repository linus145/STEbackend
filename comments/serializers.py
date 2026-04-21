from rest_framework import serializers
from .models import Comment

class CommentSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source='user.id', read_only=True)
    author_name = serializers.CharField(source='user.first_name', read_only=True)
    author_image = serializers.SerializerMethodField()
    author_linkedin_url = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ('id', 'user_id', 'author_name', 'author_image', 'author_linkedin_url', 'content', 'created_at')
        read_only_fields = ('id', 'created_at')

    def get_author_image(self, obj):
        user = obj.user
        if hasattr(user, 'founder_profile') and user.founder_profile.profile_image_url:
            return user.founder_profile.profile_image_url
        if hasattr(user, 'investor_profile') and user.investor_profile.profile_image_url:
            return user.investor_profile.profile_image_url
        return None

    def get_author_linkedin_url(self, obj):
        user = obj.user
        if hasattr(user, 'founder_profile') and user.founder_profile.linkedin_url:
            return user.founder_profile.linkedin_url
        if hasattr(user, 'investor_profile') and user.investor_profile.linkedin_url:
            return user.investor_profile.linkedin_url
        return None

class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ('post', 'content')
