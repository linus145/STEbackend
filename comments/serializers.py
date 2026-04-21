from rest_framework import serializers
from .models import Comment

class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='user.first_name', read_only=True)
    author_image = serializers.CharField(source='user.profile_image_url', read_only=True, default='') # Adjust based on user model

    class Meta:
        model = Comment
        fields = ('id', 'author_name', 'author_image', 'content', 'created_at')
        read_only_fields = ('id', 'created_at')

class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ('post', 'content')
