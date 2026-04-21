import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils import timezone
from .managers import CustomUserManager
from maincore.basemodel import SoftDeleteModel

class CustomUser(AbstractBaseUser, PermissionsMixin, SoftDeleteModel):
    ROLE_ADMIN = 'ADMIN'
    ROLE_FOUNDER = 'FOUNDER'
    ROLE_INVESTOR = 'INVESTOR'
    ROLE_MENTOR = 'MENTOR'

    ROLE_CHOICES = (
        (ROLE_ADMIN, 'Admin'),
        (ROLE_FOUNDER, 'Founder'),
        (ROLE_INVESTOR, 'Investor'),
        (ROLE_MENTOR, 'Mentor'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    phone_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_FOUNDER, db_index=True)
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)

    # LinkedIn-Style Premium Fields
    is_premium = models.BooleanField(default=False)
    is_top_voice = models.BooleanField(default=False)
    is_creator_mode = models.BooleanField(default=False)
    is_open_to_work = models.BooleanField(default=False)
    is_hiring = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.email} ({self.role})"

    def is_founder(self) -> bool:
        return self.role == self.ROLE_FOUNDER

    def is_investor(self) -> bool:
        return self.role == self.ROLE_INVESTOR

    def is_mentor(self) -> bool:
        return self.role == self.ROLE_MENTOR

    def is_admin(self) -> bool:
        return self.role == self.ROLE_ADMIN
