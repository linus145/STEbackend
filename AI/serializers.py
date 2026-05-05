from rest_framework import serializers
from .models import AIScreeningReport

class AIScreeningReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIScreeningReport
        fields = '__all__'
