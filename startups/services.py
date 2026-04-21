from django.db import transaction
from .models import Startup
from django.contrib.auth import get_user_model

User = get_user_model()

class StartupService:
    @staticmethod
    def get_startup_by_id(startup_id: str) -> Startup:
        try:
            return Startup.objects.select_related('founder').get(id=startup_id)
        except Startup.DoesNotExist:
            return None

    @staticmethod
    def get_startups_by_user(user: User):
        return Startup.objects.filter(founder=user).order_by('-created_at')

    @staticmethod
    def create_startup(user: User, validated_data: dict) -> Startup:
        with transaction.atomic():
            startup = Startup.objects.create(founder=user, **validated_data)
        return startup

    @staticmethod
    def update_startup(startup: Startup, validated_data: dict) -> Startup:
        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(startup, attr, value)
            startup.save()
        return startup

    @staticmethod
    def delete_startup(startup: Startup):
        startup.delete()

    @staticmethod
    def get_all_startups(filters: dict = None):
        """
        Retrieves startups intelligently. Used easily by generic views.
        """
        queryset = Startup.objects.select_related('founder').all()
        
        if filters:
            industry = filters.get('industry')
            if industry:
                queryset = queryset.filter(industry__icontains=industry)
            
            stage = filters.get('stage')
            if stage:
                queryset = queryset.filter(stage__icontains=stage)
                
        return queryset.order_by('-created_at')
