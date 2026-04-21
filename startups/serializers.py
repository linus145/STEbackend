from rest_framework import serializers
from .models import Startup

class StartupSerializer(serializers.ModelSerializer):
    founder_email = serializers.EmailField(source='founder.email', read_only=True)
    founder_first_name = serializers.CharField(source='founder.first_name', read_only=True)

    class Meta:
        model = Startup
        fields = (
            'id', 'founder', 'founder_email', 'founder_first_name', 
            'name', 'pitch', 'industry', 'stage', 
            'seeking_amount', 'website_url', 'logo_url', 
            'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'founder', 'created_at', 'updated_at')

class StartupCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Startup
        fields = (
            'name', 'pitch', 'industry', 'stage', 
            'seeking_amount', 'website_url', 'logo_url'
        )
