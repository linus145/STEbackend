from rest_framework import serializers
from .models import Like, Comment, Connection, MentorProfile

class LikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Like
        fields = ('id', 'user', 'post', 'created_at')
        read_only_fields = ('id', 'user', 'created_at')

class CommentSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source='user.email', read_only=True)
    author_first_name = serializers.CharField(source='user.first_name', read_only=True)
    author_headline = serializers.SerializerMethodField()
    author_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = (
            'id', 'post', 'author_email', 'author_first_name', 
            'author_headline', 'author_image_url',
            'content', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_author_headline(self, obj):
        user = obj.user
        if hasattr(user, 'founder_profile') and user.founder_profile.headline:
            return user.founder_profile.headline
        if hasattr(user, 'investor_profile') and user.investor_profile.headline:
            return user.investor_profile.headline
        if hasattr(user, 'mentor_profile') and user.mentor_profile.headline:
            return user.mentor_profile.headline
        return user.role.capitalize() if user.role else "Member"

    def get_author_image_url(self, obj):
        user = obj.user
        if hasattr(user, 'founder_profile') and user.founder_profile.profile_image_url:
            return user.founder_profile.profile_image_url
        if hasattr(user, 'investor_profile') and user.investor_profile.profile_image_url:
            return user.investor_profile.profile_image_url
        if hasattr(user, 'mentor_profile') and user.mentor_profile.profile_image_url:
            return user.mentor_profile.profile_image_url
        return None

class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ('post', 'content')


class ConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Connection
        fields = ('id', 'sender', 'receiver', 'status', 'created_at')
        read_only_fields = ('id', 'sender', 'status', 'created_at')


class MentorProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = MentorProfile
        fields = '__all__'
