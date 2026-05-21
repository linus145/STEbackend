from rest_framework import serializers
from .models import AboutUs, MissionPrinciple, Blog, JobOpening, ContactInquiry, ContactSales, Careers

class MissionPrincipleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MissionPrinciple
        fields = '__all__'

class AboutUsSerializer(serializers.ModelSerializer):
    principles = serializers.SerializerMethodField()

    class Meta:
        model = AboutUs
        fields = ['title', 'description', 'mission_statement', 'principles']

    def get_principles(self, obj):
        principles = MissionPrinciple.objects.all()
        return MissionPrincipleSerializer(principles, many=True).data

class BlogSerializer(serializers.ModelSerializer):
    class Meta:
        model = Blog
        fields = '__all__'

class JobOpeningSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobOpening
        fields = '__all__'

class CareersSerializer(serializers.ModelSerializer):
    class Meta:
        model = Careers
        fields = '__all__'

class ContactInquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactInquiry
        fields = '__all__'

class ContactSalesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactSales
        fields = '__all__'
