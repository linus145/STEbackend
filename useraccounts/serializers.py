import re
from rest_framework import serializers
from django.contrib.auth import get_user_model
from founders.serializers import FounderSerializer
from investors.serializers import InvestorSerializer

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'email', 'phone_number', 'first_name', 
            'last_name', 'role', 'is_active', 'is_verified', 
            'profile', 'created_at', 'updated_at',
            'secondary_email', 'third_email', 'is_2fa_enabled',
            'is_open_to_work', 'is_hiring', 'skills'
        )
        read_only_fields = ('id', 'is_active', 'is_verified', 'created_at', 'updated_at')

    def get_skills(self, obj):
        return list(obj.user_skills.values_list('name', flat=True))

    def get_profile(self, obj):
        from interactions.serializers import MentorProfileSerializer
        data = None
        if obj.role in [User.ROLE_FOUNDER, User.ROLE_CO_FOUNDER]:
            if hasattr(obj, 'founder_profile'):
                data = FounderSerializer(obj.founder_profile).data
        elif obj.role == User.ROLE_INVESTOR:
            if hasattr(obj, 'investor_profile'):
                data = InvestorSerializer(obj.investor_profile).data
        elif obj.role == User.ROLE_MENTOR:
            if hasattr(obj, 'mentor_profile'):
                data = MentorProfileSerializer(obj.mentor_profile).data
        elif hasattr(obj, 'employee_profile'):
            from employees.serializers import EmployeeSerializer
            data = EmployeeSerializer(obj.employee_profile).data
        
        # Add company and HR info if available
        if hasattr(obj, 'company_profile'):
            if data is None: data = {}
            data['company_name'] = obj.company_profile.company_name
            if hasattr(obj.company_profile, 'hr_profile'):
                data['hr_name'] = obj.company_profile.hr_profile.name
                data['hr_designation'] = obj.company_profile.hr_profile.designation
                
        return data

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get('request')
        
        # Only expose sensitive 2FA & backup emails to the owner themselves or staff
        if request and request.user.is_authenticated:
            if request.user == instance or request.user.is_staff:
                return ret
                
        # Otherwise, strip them for privacy & security
        ret.pop('secondary_email', None)
        ret.pop('third_email', None)
        ret.pop('is_2fa_enabled', None)
        return ret

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    class Meta:
        model = User
        fields = ('email', 'password', 'first_name', 'last_name', 'phone_number', 'role')

    def validate_password(self, value: str) -> str:
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r'\d', value):
            raise serializers.ValidationError("Password must contain at least one number.")
        return value

    def validate_role(self, value: str) -> str:
        if value == User.ROLE_ADMIN:
            raise serializers.ValidationError("Cannot register as ADMIN directly.")
        return value

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

class TokenSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()

class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate_new_password(self, value: str) -> str:
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r'\d', value):
            raise serializers.ValidationError("Password must contain at least one number.")
        return value

class UpdatePhoneNumberSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20, required=True)

    def validate_phone_number(self, value: str) -> str:
        # Basic validation for digits and optional leading plus sign
        if not re.match(r'^\+?1?\d{9,15}$', value):
            raise serializers.ValidationError("Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.")
        return value
