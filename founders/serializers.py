from rest_framework import serializers
from .models import Founder

class FounderSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)

    class Meta:
        model = Founder
        fields = (
            'id', 'user_email', 'first_name', 'last_name', 
            'headline', 'bio', 'location', 'profile_image_url', 'banner_image_url',
            'experience_years', 'primary_industry', 
            'skills', 'linkedin_url', 'portfolio_url', 
            'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

class FounderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Founder
        fields = (
            'headline', 'bio', 'location', 'profile_image_url', 'banner_image_url',
            'experience_years', 'primary_industry', 
            'skills', 'linkedin_url', 'portfolio_url'
        )
