from django.db import transaction
from .models import CompanyProfile, CompanyHRProfile, Startup
from useraccounts.services import UserService
from django.contrib.auth import get_user_model
from typing import Dict, Any

User = get_user_model()

class StartupService:
    @staticmethod
    def get_all_startups(filters: Dict[str, Any] = None):
        """
        Retrieves all startups with optimized prefetching.
        """
        from .models import Startup
        qs = Startup.objects.select_related('founder', 'founder__founder_profile')
        if filters:
            if filters.get("industry"):
                qs = qs.filter(industry=filters["industry"])
            if filters.get("stage"):
                qs = qs.filter(stage=filters["stage"])
        return qs.order_by("-created_at")

    @staticmethod
    def create_company_profile(user, validated_data):
        """
        Creates a company profile for a user.
        """
        return CompanyProfile.objects.create(owner=user, **validated_data)

    @staticmethod
    def authenticate_company(email, password):
        """
        Handles company-specific authentication and shadow user logic.
        Supports standard company password, owner password, and user fallback.
        """
        from django.contrib.auth import authenticate as django_authenticate
        
        try:
            company = CompanyProfile.objects.get(company_email=email)
            
            # 1. Try company-specific password first
            if company.company_password and company.check_company_password(password):
                if not company.owner:
                    with transaction.atomic():
                        shadow_user = User.objects.create_user(
                            email=email,
                            password=None,
                            role="FOUNDER",
                            first_name=company.company_name,
                            is_verified=True,
                        )
                        company.owner = shadow_user
                        company.save()
                return company.owner, company
                
            # 2. Try owner's account password
            if company.owner:
                authenticated_user = django_authenticate(email=company.owner.email, password=password)
                if authenticated_user == company.owner:
                    return company.owner, company
                    
            # 3. Try standard user account with matching email
            user_exists = User.objects.filter(email=email).first()
            if user_exists:
                authenticated_user = django_authenticate(email=email, password=password)
                if authenticated_user == user_exists:
                    if not company.owner:
                        company.owner = user_exists
                        company.save()
                    return user_exists, company
                    
            return None, None
        except CompanyProfile.DoesNotExist:
            # 4. Fallback if no company has this email, but a user account does and has a company profile
            user = User.objects.filter(email=email).first()
            if user:
                authenticated_user = django_authenticate(email=email, password=password)
                if authenticated_user == user and hasattr(user, 'company_profile'):
                    return user, user.company_profile
            return None, None

    @staticmethod
    def create_startup(founder, validated_data):
        return Startup.objects.create(founder=founder, **validated_data)

    @staticmethod
    def update_startup(startup, validated_data):
        for attr, value in validated_data.items():
            setattr(startup, attr, value)
        startup.save()
        return startup

    @staticmethod
    def delete_startup(startup):
        startup.delete()
        
    @staticmethod
    def get_startup_by_id(startup_id):
        return Startup.objects.filter(id=startup_id).select_related('founder').first()
        
    @staticmethod
    def get_startups_by_user(user):
        return Startup.objects.filter(founder=user).select_related('founder')
