import random
import string
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from .models import CustomUser

class EmailService:
    @staticmethod
    def generate_otp(length=6):
        """Generates a numeric OTP."""
        return ''.join(random.choices(string.digits, k=length))

    @staticmethod
    def send_otp_email(user: CustomUser):
        """Generates and sends an OTP to the user's email."""
        otp = EmailService.generate_otp()
        user.otp = otp
        user.otp_created_at = timezone.now()
        user.save(update_fields=['otp', 'otp_created_at'])

        subject = "Your B2LINQ Verification Code"
        message = f"Hello {user.first_name or 'there'},\n\nYour verification code is: {otp}\n\nThis code will expire in 10 minutes.\n\nIf you did not request this code, please ignore this email."
        
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            return True
        except Exception as e:
            print(f"Error sending email: {e}")
            return False

    @staticmethod
    def verify_otp(user: CustomUser, otp: str):
        """Verifies the OTP and marks the user as verified if correct."""
        if not user.otp or user.otp != otp:
            return False, "Invalid verification code."

        # Check expiration (10 minutes)
        if user.otp_created_at:
            expiration_time = user.otp_created_at + timezone.timedelta(minutes=10)
            if timezone.now() > expiration_time:
                return False, "Verification code has expired."

        user.is_verified = True
        user.otp = None
        user.otp_created_at = None
        user.save(update_fields=['is_verified', 'otp', 'otp_created_at'])
        return True, "Verification successful."
