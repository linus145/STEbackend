from rest_framework import serializers
from organization.models import Department, Designation, Organization

class DepartmentSerializer(serializers.ModelSerializer):
    employee_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Department
        fields = ['id', 'startup', 'name', 'description', 'employee_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class DesignationSerializer(serializers.ModelSerializer):
    employee_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Designation
        fields = ['id', 'startup', 'title', 'description', 'employee_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            'id', 'company', 'startup', 'name', 'tax_id', 'address', 'website',
            'logo_url', 'banner_url', 'industry', 'company_size', 'description', 'founded_year',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'company', 'startup', 'created_at', 'updated_at']
