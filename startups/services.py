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
        """
        try:
            company = CompanyProfile.objects.get(company_email=email)
            if company.check_company_password(password):
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
            return None, None
        except CompanyProfile.DoesNotExist:
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
