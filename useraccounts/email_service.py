import random
import string
from django.conf import settings
from django.utils import timezone
from useraccounts.models import CustomUser
from useraccounts.tasks import send_email_async

class EmailService:
    @staticmethod
    def generate_otp(length=6):
        """Generates a numeric OTP."""
        return ''.join(random.choices(string.digits, k=length))

    @staticmethod
    def send_otp_email(user: CustomUser):
        """Generates and sends an OTP to the user's email via Celery."""
        otp = EmailService.generate_otp()
        user.otp = otp
        user.otp_created_at = timezone.now()
        user.save(update_fields=['otp', 'otp_created_at'])

        company_name = "B2LINQ"
        try:
            if hasattr(user, "company_profile") and user.company_profile:
                company_name = user.company_profile.company_name
            elif hasattr(user, "employee_profile") and user.employee_profile:
                emp = user.employee_profile
                if emp.startup:
                    company_name = emp.startup.name
                elif emp.organization:
                    company_name = emp.organization.name
        except Exception:
            pass

        subject = f"Your {company_name} Verification Code"
        message = f"Hello {user.first_name or 'there'},\n\nYour verification code is: {otp}\n\nThis code will expire in 10 minutes.\n\nIf you did not request this code, please ignore this email."
        
        try:
            send_email_async.delay(
                subject,
                message,
                [user.email],
            )
            return True
        except Exception as e:
            print(f"Error triggering celery email task: {e}")
            return False

    @staticmethod
    def verify_otp(user: CustomUser, otp: str):
        """Verifies the OTP and marks the user as verified if correct."""
        from django.core.cache import cache
        import hmac

        user_id = user.id
        lockout_key = f"otp_lockout_{user_id}"
        attempts_key = f"otp_failed_attempts_{user_id}"
        
        # 1. Check lockout
        if cache.get(lockout_key):
            return False, "Too many failed attempts. Please try again in 10 minutes."
            
        # 2. Check if user has an active OTP set
        if not user.otp:
            return False, "No active verification code found."

        # 3. Check expiration (10 minutes)
        if user.otp_created_at:
            expiration_time = user.otp_created_at + timezone.timedelta(minutes=10)
            if timezone.now() > expiration_time:
                # Invalidate expired OTP
                user.otp = None
                user.otp_created_at = None
                user.save(update_fields=['otp', 'otp_created_at'])
                return False, "Verification code has expired."

        # 4. Timing-safe comparison using hmac.compare_digest
        is_valid = hmac.compare_digest(str(user.otp), str(otp))
        
        if not is_valid:
            # Increment failed attempts
            failed_count = cache.get(attempts_key, 0) + 1
            if failed_count >= 5:
                # Lock out for 10 minutes
                cache.set(lockout_key, True, timeout=600)
                cache.delete(attempts_key)
                
                # Invalidate OTP for security
                user.otp = None
                user.otp_created_at = None
                user.save(update_fields=['otp', 'otp_created_at'])
                return False, "Too many failed attempts. Verification code has been invalidated. Please request a new one."
            else:
                cache.set(attempts_key, failed_count, timeout=600)
                remaining = 5 - failed_count
                return False, f"Invalid verification code. {remaining} attempt(s) remaining."

        # 5. Success - Clear cache trackers
        cache.delete(lockout_key)
        cache.delete(attempts_key)

        user.is_verified = True
        user.otp = None
        user.otp_created_at = None
        user.save(update_fields=['is_verified', 'otp', 'otp_created_at'])
        return True, "Verification successful."

    @staticmethod
    def send_2fa_otp_emails(user: CustomUser, secondary_email: str, third_email: str):
        """Generates and sends distinct OTPs to both secondary and third emails asynchronously via Celery."""
        otp_sec = EmailService.generate_otp()
        otp_third = EmailService.generate_otp()

        user.secondary_email = secondary_email
        user.third_email = third_email
        user.secondary_email_otp = otp_sec
        user.third_email_otp = otp_third
        user.secondary_email_otp_created_at = timezone.now()
        user.third_email_otp_created_at = timezone.now()
        user.save(update_fields=[
            'secondary_email', 'third_email', 
            'secondary_email_otp', 'third_email_otp', 
            'secondary_email_otp_created_at', 'third_email_otp_created_at'
        ])

        company_name = "B2LINQ"
        try:
            if hasattr(user, "company_profile") and user.company_profile:
                company_name = user.company_profile.company_name
        except Exception:
            pass

        # Send to secondary
        subject = f"Your {company_name} 2FA Code - Secondary Email"
        message = f"Hello {user.first_name or 'there'},\n\nYour 2FA secondary email verification code is: {otp_sec}\n\nThis code will expire in 10 minutes."
        try:
            send_email_async.delay(
                subject,
                message,
                [secondary_email],
            )
        except Exception as e:
            print(f"Error triggering celery email task for secondary: {e}")

        # Send to third
        subject = f"Your {company_name} 2FA Code - Third Email"
        message = f"Hello {user.first_name or 'there'},\n\nYour 2FA third email verification code is: {otp_third}\n\nThis code will expire in 10 minutes."
        try:
            send_email_async.delay(
                subject,
                message,
                [third_email],
            )
            return True
        except Exception as e:
            print(f"Error triggering celery email task for third: {e}")
            return False

    @staticmethod
    def send_secondary_2fa_otp(user: CustomUser, secondary_email: str):
        """Generates and sends an OTP to the secondary backup email asynchronously via Celery."""
        otp_sec = EmailService.generate_otp()
        user.secondary_email = secondary_email
        user.secondary_email_otp = otp_sec
        user.secondary_email_otp_created_at = timezone.now()
        user.save(update_fields=[
            'secondary_email', 'secondary_email_otp', 'secondary_email_otp_created_at'
        ])

        company_name = "B2LINQ"
        try:
            if hasattr(user, "company_profile") and user.company_profile:
                company_name = user.company_profile.company_name
        except Exception:
            pass

        subject = f"Your {company_name} 2FA Setup Code - Secondary Email"
        message = f"Hello {user.first_name or 'there'},\n\nYour 2FA secondary email verification code is: {otp_sec}\n\nThis code will expire in 10 minutes."
        try:
            send_email_async.delay(
                subject,
                message,
                [secondary_email],
            )
            return True
        except Exception as e:
            print(f"Error triggering celery email task for secondary: {e}")
            return False

    @staticmethod
    def send_third_2fa_otp(user: CustomUser, third_email: str):
        """Generates and sends an OTP to the third backup email asynchronously via Celery."""
        otp_third = EmailService.generate_otp()
        user.third_email = third_email
        user.third_email_otp = otp_third
        user.third_email_otp_created_at = timezone.now()
        user.save(update_fields=[
            'third_email', 'third_email_otp', 'third_email_otp_created_at'
        ])

        company_name = "B2LINQ"
        try:
            if hasattr(user, "company_profile") and user.company_profile:
                company_name = user.company_profile.company_name
        except Exception:
            pass

        subject = f"Your {company_name} 2FA Setup Code - Third Email"
        message = f"Hello {user.first_name or 'there'},\n\nYour 2FA third email verification code is: {otp_third}\n\nThis code will expire in 10 minutes."
        try:
            send_email_async.delay(
                subject,
                message,
                [third_email],
            )
            return True
        except Exception as e:
            print(f"Error triggering celery email task for third: {e}")
            return False
