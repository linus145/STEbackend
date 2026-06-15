import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils import timezone
from useraccounts.managers import CustomUserManager
from maincore.basemodel import SoftDeleteModel


class CustomUser(AbstractBaseUser, PermissionsMixin, SoftDeleteModel):
    ROLE_ADMIN = "ADMIN"
    ROLE_FOUNDER = "FOUNDER"
    ROLE_CO_FOUNDER = "CO_FOUNDER"
    ROLE_INVESTOR = "INVESTOR"
    ROLE_MENTOR = "MENTOR"
    ROLE_SALES = "SALES"
    ROLE_MARKETING = "MARKETING"
    ROLE_ENGINEER = "ENGINEER"
    ROLE_PRODUCT = "PRODUCT"
    ROLE_DESIGN = "DESIGN"
    ROLE_OPERATIONS = "OPERATIONS"

    ROLE_CHOICES = (
        (ROLE_ADMIN, "Admin"),
        (ROLE_FOUNDER, "Founder"),
        (ROLE_CO_FOUNDER, "Co-Founder"),
        (ROLE_INVESTOR, "Investor"),
        (ROLE_MENTOR, "Mentor"),
        (ROLE_SALES, "Sales"),
        (ROLE_MARKETING, "Marketing"),
        (ROLE_ENGINEER, "Engineer"),
        (ROLE_PRODUCT, "Product Manager"),
        (ROLE_DESIGN, "Designer"),
        (ROLE_OPERATIONS, "Operations"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    phone_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default=ROLE_FOUNDER, db_index=True
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)
    google_id = models.CharField(max_length=255, unique=True, blank=True, null=True)

    # Multi-Email 2FA Fields
    secondary_email = models.EmailField(blank=True, null=True)
    third_email = models.EmailField(blank=True, null=True)
    secondary_email_otp = models.CharField(max_length=6, blank=True, null=True)
    third_email_otp = models.CharField(max_length=6, blank=True, null=True)
    secondary_email_otp_created_at = models.DateTimeField(blank=True, null=True)
    third_email_otp_created_at = models.DateTimeField(blank=True, null=True)
    is_2fa_enabled = models.BooleanField(default=False)

    # LinkedIn-Style Premium Fields
    is_premium = models.BooleanField(default=False)
    is_top_voice = models.BooleanField(default=False)
    is_creator_mode = models.BooleanField(default=False)
    is_open_to_work = models.BooleanField(default=False)
    is_hiring = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-created_at"]

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

class WsTicket(models.Model):
    """
    A short-lived, one-time use ticket for WebSocket authentication.
    Prevents exposure of raw JWT tokens to frontend JS.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="ws_tickets")
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def is_valid(self):
        # Tickets expire after 30 seconds
        expiration_time = self.created_at + timezone.timedelta(seconds=30)
        return not self.is_used and timezone.now() < expiration_time


class UserSkill(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="user_skills",
        db_index=True,
    )
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "User Skill"
        verbose_name_plural = "User Skills"
        unique_together = ("user", "name")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.user.email} - {self.name}"

