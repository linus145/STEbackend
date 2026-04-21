from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from .models import Founder
from django.contrib.auth import get_user_model

User = get_user_model()

class FounderService:
    @staticmethod
    def get_founder_by_id(founder_id: str) -> Founder:
        try:
            # Optimize with select_related for user data
            return Founder.objects.select_related('user').get(id=founder_id)
        except Founder.DoesNotExist:
            return None

    @staticmethod
    def get_founder_by_user(user: User) -> Founder:
        try:
            return Founder.objects.select_related('user').get(user=user)
        except Founder.DoesNotExist:
            return None

    @staticmethod
    def create_or_update_profile(user: User, validated_data: dict) -> Founder:
        """
        Creates or updates a founder profile safely within a transaction.
        """
        with transaction.atomic():
            founder, created = Founder.objects.update_or_create(
                user=user,
                defaults=validated_data
            )
        return founder

    @staticmethod
    def get_all_founders(filters: dict = None):
        """
        Retrieves founders with optional filtering safely.
        """
        queryset = Founder.objects.select_related('user').all()
        
        if filters:
            industry = filters.get('primary_industry')
            if industry:
                queryset = queryset.filter(primary_industry__icontains=industry)
                
            min_experience = filters.get('min_experience')
            if min_experience:
                queryset = queryset.filter(experience_years__gte=min_experience)
                
        return queryset.order_by('-created_at')
