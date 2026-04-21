from rest_framework import serializers
from .models import Investor

class InvestorSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)

    class Meta:
        model = Investor
        fields = (
            'id', 'user_email', 'first_name', 'last_name', 
            'headline', 'bio', 'location', 'profile_image_url',
            'firm_name', 'preferred_stages', 'preferred_industries',
            'minimum_investment_range', 'maximum_investment_range',
            'linkedin_url', 'portfolio_url', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

class InvestorUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Investor
        fields = (
            'headline', 'bio', 'location', 'profile_image_url',
            'firm_name', 'preferred_stages', 'preferred_industries',
            'minimum_investment_range', 'maximum_investment_range',
            'linkedin_url', 'portfolio_url'
        )
