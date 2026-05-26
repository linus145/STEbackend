from rest_framework import serializers
from employees.models import (
    Employee, EmployeeProfile, EmergencyContact, EmployeeDocument,
    EmployeeAadhaarDetail, EmployeePANDetail, EmployeeJoiningDetail,
    EmployeeBankDetail
)
from organization.serializers import DepartmentSerializer, DesignationSerializer
from organization.models import Department, Designation

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

class EmployeeAadhaarDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeAadhaarDetail
        exclude = ['employee', 'organization']

class EmployeePANDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeePANDetail
        exclude = ['employee', 'organization']

class EmployeeJoiningDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeJoiningDetail
        exclude = ['employee', 'organization']

class EmployeeBankDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeeBankDetail
        exclude = ['employee', 'organization']

class EmployeeSerializer(serializers.ModelSerializer):
    department_detail = DepartmentSerializer(source='department', read_only=True)
    designation_detail = DesignationSerializer(source='designation', read_only=True)
    profile_details = EmployeeProfileSerializer(read_only=True)
    
    designation = serializers.PrimaryKeyRelatedField(
        queryset=Designation.objects.all(),
        required=False,
        allow_null=True
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        required=False,
        allow_null=True
    )
    
    aadhaar_detail = EmployeeAadhaarDetailSerializer(required=False, allow_null=True)
    pan_detail = EmployeePANDetailSerializer(required=False, allow_null=True)
    joining_detail = EmployeeJoiningDetailSerializer(required=False, allow_null=True)
    bank_detail = EmployeeBankDetailSerializer(required=False, allow_null=True)
    
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = Employee
        fields = [
            'id', 'startup', 'user', 'employee_id', 'first_name', 'last_name', 
            'email', 'phone', 'designation', 'designation_detail', 
            'department', 'department_detail', 'joining_date', 
            'employment_type', 'reporting_manager', 'salary', 'avatar', 
            'address', 'status', 'profile_details', 'job_application', 
            'aadhaar_detail', 'pan_detail', 'joining_detail', 'bank_detail',
            'created_at', 'updated_at', 'portal_username', 'portal_password', 'password'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'employee_id': {'required': False, 'allow_blank': True}
        }

    def create(self, validated_data):
        aadhaar_data = validated_data.pop('aadhaar_detail', None)
        pan_data = validated_data.pop('pan_detail', None)
        joining_data = validated_data.pop('joining_detail', None)
        bank_data = validated_data.pop('bank_detail', None)
        
        # 1. Automatically generate portal_username if not provided
        portal_username = validated_data.get('portal_username')
        if not portal_username:
            first_name = validated_data.get('first_name', 'emp').lower().replace(' ', '')
            base_uname = f"emp_{first_name}"
            unique_uname = base_uname
            counter = 1
            while Employee.all_objects.filter(portal_username=unique_uname).exists():
                unique_uname = f"{base_uname}{counter}"
                counter += 1
            portal_username = unique_uname
            validated_data['portal_username'] = portal_username

        # 2. Automatically generate a placeholder password for the User account
        #    (The actual password will be set later via the send-credentials endpoint)
        import random
        import string
        chars = string.ascii_letters + string.digits
        auto_password = 'B2lq_' + ''.join(random.choice(chars) for _ in range(8))
            
        # 3. Securely register the User account for authorization
        from django.contrib.auth import get_user_model
        User = get_user_model()
        email = validated_data.get('email')
        user = User.objects.filter(email=email).first()
        if not user:
            user = User.objects.create_user(
                email=email,
                password=auto_password,
                first_name=validated_data.get('first_name', ''),
                last_name=validated_data.get('last_name', ''),
                role='OPERATIONS'
            )
        else:
            # Clear link on any soft-deleted employees to prevent IntegrityError
            Employee.all_objects.filter(user=user, is_deleted=True).update(user=None)
            
            # Check if linked to an active employee
            if Employee.objects.filter(user=user).exists():
                raise serializers.ValidationError({
                    "email": "This email is already registered and linked to an active employee profile."
                })
                
            # Update user's name and role to employee operations defaults
            user.first_name = validated_data.get('first_name', '')
            user.last_name = validated_data.get('last_name', '')
            user.role = 'OPERATIONS'
            user.set_password(auto_password)
            user.save()
        validated_data['user'] = user
        
        instance = super().create(validated_data)
        
        # NOTE: No credentials email is sent during creation.
        # The HR admin should go to the employee details page, set the password,
        # and use the "Set Password & Send Credentials" button to send the email.
        
        if aadhaar_data is not None:
            EmployeeAadhaarDetail.objects.create(employee=instance, organization=instance.organization, **aadhaar_data)
        else:
            EmployeeAadhaarDetail.objects.get_or_create(employee=instance, organization=instance.organization)
            
        if pan_data is not None:
            EmployeePANDetail.objects.create(employee=instance, organization=instance.organization, **pan_data)
        else:
            EmployeePANDetail.objects.get_or_create(employee=instance, organization=instance.organization)
            
        if joining_data is not None:
            EmployeeJoiningDetail.objects.create(employee=instance, organization=instance.organization, **joining_data)
        else:
            EmployeeJoiningDetail.objects.get_or_create(
                employee=instance, 
                organization=instance.organization, 
                defaults={'joining_date': instance.joining_date}
            )
            
        if bank_data is not None:
            EmployeeBankDetail.objects.create(employee=instance, organization=instance.organization, **bank_data)
        else:
            EmployeeBankDetail.objects.get_or_create(employee=instance, organization=instance.organization)
            
        return instance

    def update(self, instance, validated_data):
        aadhaar_data = validated_data.pop('aadhaar_detail', None)
        pan_data = validated_data.pop('pan_detail', None)
        joining_data = validated_data.pop('joining_detail', None)
        bank_data = validated_data.pop('bank_detail', None)
        
        password = validated_data.pop('password', None)
        if password:
            # Store plaintext password for HR admin visibility
            instance.portal_password = password
            instance.save()
            
            # Set hashed password on the Django User account
            from django.contrib.auth import get_user_model
            User = get_user_model()
            if not instance.user:
                email = validated_data.get('email', instance.email)
                user = User.objects.filter(email=email).first()
                if not user:
                    user = User.objects.create_user(
                        email=email,
                        password=password,
                        first_name=validated_data.get('first_name', instance.first_name),
                        last_name=validated_data.get('last_name', instance.last_name),
                        role='OPERATIONS'
                    )
                else:
                    Employee.all_objects.filter(user=user, is_deleted=True).update(user=None)
                    if Employee.objects.filter(user=user).exclude(id=instance.id).exists():
                        raise serializers.ValidationError({
                            "email": "This email is already registered and linked to an active employee profile."
                        })
                    user.set_password(password)
                    user.save()
                instance.user = user
                instance.save()
            else:
                instance.user.set_password(password)
                instance.user.save()
            
            # Send credentials email with the actual password
            try:
                from employees.services import EmployeeService
                request = self.context.get('request')
                host_meta = request.META.get('HTTP_HOST') if request else None
                absolute_uri_fn = request.build_absolute_uri if request else None
                EmployeeService.send_credentials_email(
                    employee=instance,
                    host_meta=host_meta,
                    absolute_uri_fn=absolute_uri_fn,
                    temp_password=password
                )
            except Exception as e:
                print(f"Failed to send credentials email: {e}")

        instance = super().update(instance, validated_data)
        
        if aadhaar_data is not None:
            detail, _ = EmployeeAadhaarDetail.objects.get_or_create(
                employee=instance,
                defaults={'organization': instance.organization}
            )
            for k, v in aadhaar_data.items():
                setattr(detail, k, v)
            detail.save()
            
        if pan_data is not None:
            detail, _ = EmployeePANDetail.objects.get_or_create(
                employee=instance,
                defaults={'organization': instance.organization}
            )
            for k, v in pan_data.items():
                setattr(detail, k, v)
            detail.save()
            
        if joining_data is not None:
            detail, _ = EmployeeJoiningDetail.objects.get_or_create(
                employee=instance,
                defaults={'organization': instance.organization}
            )
            for k, v in joining_data.items():
                setattr(detail, k, v)
            detail.save()
            
            # Sync core joining_date
            if 'joining_date' in joining_data:
                instance.joining_date = joining_data['joining_date']
                instance.save()
                
        if bank_data is not None:
            detail, _ = EmployeeBankDetail.objects.get_or_create(
                employee=instance,
                defaults={'organization': instance.organization}
            )
            for k, v in bank_data.items():
                setattr(detail, k, v)
            detail.save()
                
        return instance

class EmployeeDetailSerializer(EmployeeSerializer):
    emergency_contacts = EmergencyContactSerializer(many=True, read_only=True)
    documents = EmployeeDocumentSerializer(many=True, read_only=True)
    
    class Meta(EmployeeSerializer.Meta):
        fields = EmployeeSerializer.Meta.fields + ['emergency_contacts', 'documents']
