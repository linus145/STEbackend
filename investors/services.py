from django.db import transaction
from .models import Investor
from django.contrib.auth import get_user_model

User = get_user_model()

class InvestorService:
    @staticmethod
    def get_investor_by_id(investor_id: str) -> Investor:
        try:
            return Investor.objects.select_related('user').get(id=investor_id)
        except Investor.DoesNotExist:
            return None

    @staticmethod
    def get_investor_by_user(user: User) -> Investor:
        try:
            return Investor.objects.select_related('user').get(user=user)
        except Investor.DoesNotExist:
            return None

    @staticmethod
    def create_or_update_profile(user: User, validated_data: dict) -> Investor:
        with transaction.atomic():
            investor, created = Investor.objects.update_or_create(
                user=user,
                defaults=validated_data
            )
        return investor

    @staticmethod
    def get_all_investors(filters: dict = None):
        """
        Robust querying over Investor fields. Future proofing for JSON querying constraints.
        """
        queryset = Investor.objects.select_related('user').all()
        
        # We can implement basic string search over firm names for now.
        if filters:
            firm = filters.get('firm_name')
            if firm:
                queryset = queryset.filter(firm_name__icontains=firm)
                
        return queryset.order_by('-created_at')
