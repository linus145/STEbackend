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

    class Meta:
        model = Comment
        fields = (
            'id', 'post', 'author_email', 'author_first_name', 
            'content', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

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
