from rest_framework import serializers
from employees.models import Employee, EmployeeProfile, EmergencyContact, EmployeeDocument
from organization.serializers import DepartmentSerializer, DesignationSerializer

class EmployeeProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeProfile
        exclude = ['employee']

class EmergencyContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyContact
        fields = '__all__'

class EmployeeDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeDocument
        fields = '__all__'

class EmployeeSerializer(serializers.ModelSerializer):
    department_detail = DepartmentSerializer(source='department', read_only=True)
    designation_detail = DesignationSerializer(source='designation', read_only=True)
    profile_details = EmployeeProfileSerializer(read_only=True)
    
    class Meta:
        model = Employee
        fields = [
            'id', 'startup', 'user', 'employee_id', 'first_name', 'last_name', 
            'email', 'phone', 'designation', 'designation_detail', 
            'department', 'department_detail', 'joining_date', 
            'employment_type', 'reporting_manager', 'salary', 'avatar', 
            'address', 'status', 'profile_details', 'job_application', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'employee_id': {'required': False, 'allow_blank': True}
        }

class EmployeeDetailSerializer(EmployeeSerializer):
    emergency_contacts = EmergencyContactSerializer(many=True, read_only=True)
    documents = EmployeeDocumentSerializer(many=True, read_only=True)
    
    class Meta(EmployeeSerializer.Meta):
        fields = EmployeeSerializer.Meta.fields + ['emergency_contacts', 'documents']
