from rest_framework import serializers
from .models import Post

class PostSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source='author.email', read_only=True)
    author_first_name = serializers.CharField(source='author.first_name', read_only=True)
    author_role = serializers.CharField(source='author.role', read_only=True)
    
    # These will be dynamically injected via queryset annotations in the service layer
    likes_count = serializers.IntegerField(read_only=True, default=0)
    comments_count = serializers.IntegerField(read_only=True, default=0)
    user_has_liked = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Post
        fields = (
            'id', 'author_email', 'author_first_name', 'author_role', 
            'content', 'media_url', 'likes_count', 'comments_count', 
            'user_has_liked', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

class PostCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ('content', 'media_url')
