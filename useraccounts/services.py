from django.contrib.auth import get_user_model, authenticate
from django.db import transaction
from typing import Dict, Any, Tuple
from rest_framework_simplejwt.tokens import RefreshToken
from founders.models import Founder
from investors.models import Investor

User = get_user_model()

class UserService:
    @staticmethod
    def create_user(validated_data: Dict[str, Any]) -> User:
        """
        Creates a structurally valid user safely within an atomic transaction.
        Also initializes the corresponding profile (Founder or Investor).
        """
        with transaction.atomic():
            user = User.objects.create_user(
                email=validated_data.get('email'),
                password=validated_data.get('password'),
                first_name=validated_data.get('first_name', ''),
                last_name=validated_data.get('last_name', ''),
                phone_number=validated_data.get('phone_number', None),
                role=validated_data.get('role', User.ROLE_FOUNDER)
            )
            
            # Create profile based on role
            if user.role == User.ROLE_FOUNDER:
                Founder.objects.create(user=user)
            elif user.role == User.ROLE_INVESTOR:
                Investor.objects.create(user=user)
                
        return user

    @staticmethod
    def authenticate_user(email: str, password: str) -> User:
        """
        Validates login credentials seamlessly. Returns user or None.
        """
        return authenticate(email=email, password=password)

    @staticmethod
    def generate_tokens(user: User) -> Dict[str, str]:
        """
        Generates JWT Access and Refresh tokens for a given user.
        """
        refresh = RefreshToken.for_user(user)
        # We can add custom claims generically here if needed
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }

    @staticmethod
    def logout_user(refresh_token: str) -> bool:
        """
        Blacklists a JWT Refresh token safely.
        """
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return True
        except Exception:
            return False

    @staticmethod
    def verify_user(user: User) -> User:
        """
        Marks user as verified safely.
        """
        user.is_verified = True
        user.save(update_fields=['is_verified'])
        return user

    @staticmethod
    def get_or_create_google_user(email: str, first_name: str, last_name: str, google_id: str) -> User:
        """
        Retrieves an existing user by email or google_id, or creates a new one.
        Ensures the user is verified and google_id is linked.
        """
        user = User.objects.filter(google_id=google_id).first()
        if not user:
            user = User.objects.filter(email=email).first()
            if user:
                # Link existing user to google_id
                user.google_id = google_id
                user.is_verified = True
                user.save(update_fields=['google_id', 'is_verified'])
            else:
                # Create new user
                with transaction.atomic():
                    user = User.objects.create_user(
                        email=email,
                        password=None,  # Google users don't need a local password initially
                        first_name=first_name,
                        last_name=last_name,
                        role=User.ROLE_FOUNDER, # Default role
                        google_id=google_id,
                        is_verified=True
                    )
                    # Create default profile
                    Founder.objects.create(user=user)
        return user
