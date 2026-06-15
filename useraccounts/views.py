from django.db import models
from django.db.models import Count
from django.conf import settings
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth import get_user_model
from django.core.mail import send_mail, get_connection
from django.template.loader import render_to_string
from django.utils import timezone

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated

from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken

from google.oauth2 import id_token
from google.auth.transport import requests

from maincore.imagekit_utils import ImageKitService
from founders.serializers import FounderUpdateSerializer
from founders.models import Founder
from investors.serializers import InvestorUpdateSerializer
from investors.models import Investor
from startups.models import CompanyProfile
from chat.models import ChatRoom, Message as ChatMessage
from employees.views import _delete_employee_auth_cookies, _set_employee_auth_cookies

from useraccounts.serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
    LogoutSerializer,
    ChangePasswordSerializer,
    UpdatePhoneNumberSerializer,
)
from useraccounts.services import UserService
from useraccounts.models import CustomUser, WsTicket
from useraccounts.email_service import EmailService



class RequestResponseMixin:
    """Helper to maintain standardized structured JSON output globally"""

    def build_response(
        self,
        status_msg: str,
        message: str,
        data: dict = None,
        status_code: int = status.HTTP_200_OK,
    ):
        payload = {
            "status": status_msg,
            "message": message,
            "data": data if data else {},
        }
        return Response(payload, status=status_code)


def _set_auth_cookies(response, access_token, refresh_token):
    """Centralized cookie setter — ensures consistent cookie config everywhere."""
    jwt_settings = settings.SIMPLE_JWT
    response.set_cookie(
        key=jwt_settings["AUTH_COOKIE"],
        value=access_token,
        expires=jwt_settings["ACCESS_TOKEN_LIFETIME"],
        secure=jwt_settings["AUTH_COOKIE_SECURE"],
        httponly=jwt_settings["AUTH_COOKIE_HTTP_ONLY"],
        samesite=jwt_settings["AUTH_COOKIE_SAMESITE"],
        path=jwt_settings.get("AUTH_COOKIE_PATH", "/"),
    )
    response.set_cookie(
        key=jwt_settings["AUTH_COOKIE_REFRESH"],
        value=refresh_token,
        expires=jwt_settings["REFRESH_TOKEN_LIFETIME"],
        secure=jwt_settings["AUTH_COOKIE_SECURE"],
        httponly=jwt_settings["AUTH_COOKIE_HTTP_ONLY"],
        samesite=jwt_settings["AUTH_COOKIE_SAMESITE"],
        path=jwt_settings.get("AUTH_COOKIE_PATH", "/"),
    )
    return response


def _delete_auth_cookies(response):
    """Centralized cookie deletion — ensures consistent cleanup."""
    jwt_settings = settings.SIMPLE_JWT
    response.delete_cookie(
        jwt_settings["AUTH_COOKIE"],
        path=jwt_settings.get("AUTH_COOKIE_PATH", "/"),
    )
    response.delete_cookie(
        jwt_settings["AUTH_COOKIE_REFRESH"],
        path=jwt_settings.get("AUTH_COOKIE_PATH", "/"),
    )
    return response


class RegisterView(APIView, RequestResponseMixin):
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = UserService.create_user(serializer.validated_data)
            user_data = UserSerializer(user).data
            return self.build_response(
                status_msg="success",
                message="User registered successfully. Please verify your email.",
                data={"user": user_data},
                status_code=status.HTTP_201_CREATED,
            )
        return self.build_response(
            "error", "Validation failed", serializer.errors, status.HTTP_400_BAD_REQUEST
        )


from maincore.throttling import LoginBurstThrottle, LoginSustainedThrottle

class LoginView(APIView, RequestResponseMixin):
    permission_classes = (AllowAny,)
    throttle_classes = [LoginBurstThrottle, LoginSustainedThrottle]

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            password = serializer.validated_data["password"]
            user = UserService.authenticate_user(email, password)
            if user:
                if not user.is_verified:
                    return self.build_response(
                        "error", 
                        "Email not verified. Please verify your email using OTP.", 
                        {"email": user.email, "is_verified": False}, 
                        status.HTTP_403_FORBIDDEN
                    )
                tokens = UserService.generate_tokens(user)
                response = self.build_response(
                    status_msg="success",
                    message="Login successful.",
                    data={"user": UserSerializer(user).data},
                    status_code=status.HTTP_200_OK,
                )
                _set_auth_cookies(response, tokens["access"], tokens["refresh"])
                return response
            return self.build_response(
                "error", "Invalid credentials.", {}, status.HTTP_401_UNAUTHORIZED
            )
        return self.build_response(
            "error",
            "Validation failed.",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST,
        )


class LogoutView(APIView, RequestResponseMixin):
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get(
            settings.SIMPLE_JWT.get("AUTH_COOKIE_REFRESH", "refresh_token")
        )
        if refresh_token:
            UserService.logout_user(refresh_token)

        response = self.build_response(
            "success", "Logged out successfully.", {}, status.HTTP_200_OK
        )
        _delete_auth_cookies(response)
        return response


class ProfileView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        serializer = UserSerializer(request.user)
        return self.build_response(
            "success",
            "Profile fetched successfully.",
            serializer.data,
            status.HTTP_200_OK,
        )

    def patch(self, request, *args, **kwargs):
        user = request.user
        data = request.data

        # Split data into user fields and profile fields
        user_fields = ["first_name", "last_name", "phone_number", "is_open_to_work", "is_hiring"]
        user_data = {k: v for k, v in data.items() if k in user_fields}
        profile_data = {k: v for k, v in data.items() if k not in user_fields}

        # Sync UserSkill table
        skills_data = profile_data.pop("skills", None)
        if skills_data is not None:
            user.user_skills.all().delete()
            from useraccounts.models import UserSkill
            for s_name in skills_data:
                if s_name.strip():
                    UserSkill.objects.get_or_create(user=user, name=s_name.strip())


        # Update User
        if user_data:
            user_serializer = UserSerializer(user, data=user_data, partial=True)
            if user_serializer.is_valid():
                user_serializer.save()
            else:
                return self.build_response(
                    "error",
                    "User validation failed",
                    user_serializer.errors,
                    status.HTTP_400_BAD_REQUEST,
                )

        # Update Profile
        if profile_data:

            profile_obj = None
            if user.role == user.ROLE_FOUNDER:
                if not hasattr(user, "founder_profile"):
                    Founder.objects.create(user=user)
                profile_obj = user.founder_profile
                profile_serializer = FounderUpdateSerializer(
                    profile_obj, data=profile_data, partial=True
                )
            elif user.role == user.ROLE_INVESTOR:
                if not hasattr(user, "investor_profile"):
                    Investor.objects.create(user=user)
                profile_obj = user.investor_profile
                profile_serializer = InvestorUpdateSerializer(
                    profile_obj, data=profile_data, partial=True
                )
            else:
                return self.build_response(
                    "error",
                    "Invalid user role for profile update",
                    {},
                    status.HTTP_400_BAD_REQUEST,
                )

            if profile_serializer.is_valid():
                # Track old images for cleanup
                old_profile_image = (
                    profile_obj.profile_image_url if profile_obj else None
                )
                old_banner_image = profile_obj.banner_image_url if profile_obj else None

                new_profile_image = profile_data.get("profile_image_url")
                new_banner_image = profile_data.get("banner_image_url")

                profile_serializer.save()

                # Perform cleanup if URLs changed and actually exist
                if (
                    new_profile_image
                    and old_profile_image
                    and new_profile_image != old_profile_image
                ):
                    ImageKitService.delete_file(old_profile_image)

                if (
                    new_banner_image
                    and old_banner_image
                    and new_banner_image != old_banner_image
                ):
                    ImageKitService.delete_file(old_banner_image)
            else:
                return self.build_response(
                    "error",
                    "Profile validation failed",
                    profile_serializer.errors,
                    status.HTTP_400_BAD_REQUEST,
                )

        return self.build_response(
            "success",
            "Profile updated successfully.",
            UserSerializer(user).data,
            status.HTTP_200_OK,
        )


class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        # 1. Try reading the employee-specific refresh cookie first
        is_employee = "employee_refresh_token" in request.COOKIES
        refresh_token = request.COOKIES.get("employee_refresh_token")

        # 2. Fallback to standard refresh cookie
        if not refresh_token:
            refresh_token = request.COOKIES.get(
                settings.SIMPLE_JWT.get("AUTH_COOKIE_REFRESH", "refresh_token")
            )

        if not refresh_token:
            # No refresh cookie → controlled 401, no crash
            response = Response(
                {"detail": "No refresh token provided", "code": "token_missing"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            _delete_auth_cookies(response)
            if is_employee:
                _delete_employee_auth_cookies(response)
            return response

        # Safely copy request data natively to avoid immutability issues
        data = (
            request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        )
        data["refresh"] = refresh_token

        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            response = Response(
                {"detail": "Token is invalid or expired", "code": "token_not_valid"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            _delete_auth_cookies(response)
            if is_employee:
                _delete_employee_auth_cookies(response)
            return response

        access_token = serializer.validated_data.get("access")
        refresh_token_new = serializer.validated_data.get("refresh")

        response = Response(
            {"status": "success", "message": "Tokens refreshed"},
            status=status.HTTP_200_OK,
        )

        if is_employee:
            _set_employee_auth_cookies(response, access_token, refresh_token_new or refresh_token)
        else:
            jwt_settings = settings.SIMPLE_JWT
            response.set_cookie(
                key=jwt_settings["AUTH_COOKIE"],
                value=access_token,
                expires=jwt_settings["ACCESS_TOKEN_LIFETIME"],
                secure=jwt_settings["AUTH_COOKIE_SECURE"],
                httponly=jwt_settings["AUTH_COOKIE_HTTP_ONLY"],
                samesite=jwt_settings["AUTH_COOKIE_SAMESITE"],
                path=jwt_settings.get("AUTH_COOKIE_PATH", "/"),
            )

            if refresh_token_new:
                response.set_cookie(
                    key=jwt_settings["AUTH_COOKIE_REFRESH"],
                    value=refresh_token_new,
                    expires=jwt_settings["REFRESH_TOKEN_LIFETIME"],
                    secure=jwt_settings["AUTH_COOKIE_SECURE"],
                    httponly=jwt_settings["AUTH_COOKIE_HTTP_ONLY"],
                    samesite=jwt_settings["AUTH_COOKIE_SAMESITE"],
                    path=jwt_settings.get("AUTH_COOKIE_PATH", "/"),
                )

        return response


class WsTicketView(APIView):
    """
    Returns a one-time use ticket (UUID) for WebSocket authentication.
    Prevents HttpOnly cookie bypass or raw JWT exposure in query strings.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        ticket = WsTicket.objects.create(user=request.user)
        return Response({"token": str(ticket.id)}, status=status.HTTP_200_OK)


class PublicProfileView(APIView, RequestResponseMixin):
    permission_classes = (AllowAny,)

    def get(self, request, user_id, *args, **kwargs):
        try:
            user = CustomUser.objects.get(id=user_id)
            serializer = UserSerializer(user)
            return self.build_response(
                "success",
                "Public profile fetched successfully.",
                serializer.data,
                status.HTTP_200_OK,
            )
        except (CustomUser.DoesNotExist, ValueError):
            return self.build_response(
                "error", "User not found.", {}, status.HTTP_404_NOT_FOUND
            )


class ChangePasswordView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        user = request.user
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            old_password = serializer.validated_data.get("old_password")
            new_password = serializer.validated_data.get("new_password")

            if not user.check_password(old_password):
                return self.build_response(
                    "error",
                    "Incorrect current password",
                    {},
                    status.HTTP_400_BAD_REQUEST,
                )

            # If 2FA is enabled, check for OTP verification before changing password
            if user.is_2fa_enabled:
                secondary_otp = request.data.get("secondary_otp")
                third_otp = request.data.get("third_otp")

                # If OTPs are not provided, generate and send them
                if not secondary_otp or not third_otp:
                    if EmailService.send_2fa_otp_emails(user, user.secondary_email, user.third_email):
                        return self.build_response(
                            "2fa_required",
                            "Verification codes have been sent to both backup emails.",
                            {},
                            status.HTTP_200_OK
                        )
                    return self.build_response(
                        "error",
                        "Failed to send 2FA codes. Please try again.",
                        {},
                        status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

                # Verify secondary email OTP
                if not user.secondary_email_otp or user.secondary_email_otp != secondary_otp:
                    return self.build_response("error", "Invalid secondary email verification code.", {}, status.HTTP_400_BAD_REQUEST)

                if user.secondary_email_otp_created_at:
                    expiration = user.secondary_email_otp_created_at + timezone.timedelta(minutes=10)
                    if timezone.now() > expiration:
                        return self.build_response("error", "Secondary email verification code has expired.", {}, status.HTTP_400_BAD_REQUEST)

                # Verify third email OTP
                if not user.third_email_otp or user.third_email_otp != third_otp:
                    return self.build_response("error", "Invalid third email verification code.", {}, status.HTTP_400_BAD_REQUEST)

                if user.third_email_otp_created_at:
                    expiration = user.third_email_otp_created_at + timezone.timedelta(minutes=10)
                    if timezone.now() > expiration:
                        return self.build_response("error", "Third email verification code has expired.", {}, status.HTTP_400_BAD_REQUEST)

                # Clear OTP fields on successful validation
                user.secondary_email_otp = None
                user.third_email_otp = None
                user.secondary_email_otp_created_at = None
                user.third_email_otp_created_at = None
                user.save()

            user.set_password(new_password)
            user.save()
            return self.build_response(
                "success", "Password updated successfully", {}, status.HTTP_200_OK
            )
        return self.build_response(
            "error", "Validation failed", serializer.errors, status.HTTP_400_BAD_REQUEST
        )


class UpdatePhoneNumberView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        user = request.user
        serializer = UpdatePhoneNumberSerializer(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data.get("phone_number")

            # Check if this phone number is already registered to another user
            User = get_user_model()
            if (
                User.objects.filter(phone_number=phone_number)
                .exclude(id=user.id)
                .exists()
            ):
                return self.build_response(
                    "error",
                    "This phone number is already registered.",
                    {},
                    status.HTTP_400_BAD_REQUEST,
                )

            user.phone_number = phone_number
            user.save()
            return self.build_response(
                "success",
                "Phone number updated successfully",
                {"phone_number": phone_number},
                status.HTTP_200_OK,
            )
        return self.build_response(
            "error", "Validation failed", serializer.errors, status.HTTP_400_BAD_REQUEST
        )


@method_decorator(csrf_exempt, name="dispatch")
class GoogleLoginView(APIView, RequestResponseMixin):
    permission_classes = (AllowAny,)
    throttle_classes = [LoginBurstThrottle, LoginSustainedThrottle]

    def post(self, request, *args, **kwargs):
        import logging
        logger = logging.getLogger(__name__)

        # 1. Validate Google's CSRF double-submit cookie protection
        csrf_token_cookie = request.COOKIES.get("g_csrf_token")
        csrf_token_body = request.data.get("g_csrf_token") or request.POST.get("g_csrf_token")
        if not csrf_token_cookie or not csrf_token_body or csrf_token_cookie != csrf_token_body:
            logger.warning("CSRF validation failed for Google OAuth request.")
            return redirect(f"{settings.FRONTEND_URL}/login?error=csrf_error")

        # In redirect mode, Google sends data as form-data
        token = request.data.get("credential") or request.POST.get("credential")

        if not token:
            logger.warning("No Google OAuth credential found in request.")
            return redirect(f"{settings.FRONTEND_URL}/login?error=no_token")

        try:
            logger.info("Verifying Google OAuth Token...")
            idinfo = id_token.verify_oauth2_token(
                token, requests.Request(), settings.GOOGLE_OAUTH_CLIENT_ID
            )

            google_id = idinfo["sub"]
            email = idinfo["email"]
            logger.info("Google OAuth User verified successfully.")

            first_name = idinfo.get("given_name", "")
            last_name = idinfo.get("family_name", "")

            user = UserService.get_or_create_google_user(
                email, first_name, last_name, google_id
            )

            tokens = UserService.generate_tokens(user)

            # Create response that redirects back to frontend dashboard
            response = redirect(f"{settings.FRONTEND_URL}/dashboard")
            _set_auth_cookies(response, tokens["access"], tokens["refresh"])
            return response

        except ValueError as e:
            logger.error(f"Google Token verification failed: {str(e)}")
            return redirect(f"{settings.FRONTEND_URL}/login?error=invalid_token")
        except Exception as e:
            logger.exception(f"Google Login Error: {str(e)}")
            return redirect(f"{settings.FRONTEND_URL}/login?error=server_error")


class UserListView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        # 1. Authorization check: Only recruiters or staff can view the candidate list
        is_authorized = (
            request.user.is_staff or 
            request.user.role in [
                CustomUser.ROLE_ADMIN,
                CustomUser.ROLE_FOUNDER,
                CustomUser.ROLE_CO_FOUNDER,
                CustomUser.ROLE_INVESTOR,
            ] or 
            hasattr(request.user, 'employee_profile')
        )
        if not is_authorized:
            return self.build_response("error", "Only recruiters or founders are authorized to view candidates.", {}, status.HTTP_403_FORBIDDEN)

        # 2. Optimized Query with select_related & prefetch_related to solve N+1 database queries
        users = CustomUser.objects.exclude(
            models.Q(role=CustomUser.ROLE_ADMIN) | models.Q(is_staff=True)
        ).select_related(
            'founder_profile', 'investor_profile', 'company_profile'
        ).prefetch_related(
            'employee_profile', 'employee_profile__startup', 'employee_profile__organization'
        )
        
        serializer = UserSerializer(users, many=True, context={'request': request})
        return self.build_response(
            "success",
            "Users fetched successfully.",
            serializer.data,
            status.HTTP_200_OK,
        )


class RecruiterContactView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        # 1. Authorization check: Only recruiters or staff can contact candidates
        is_authorized = (
            request.user.is_staff or 
            request.user.role in [
                CustomUser.ROLE_ADMIN,
                CustomUser.ROLE_FOUNDER,
                CustomUser.ROLE_CO_FOUNDER,
                CustomUser.ROLE_INVESTOR,
            ] or 
            hasattr(request.user, 'employee_profile')
        )
        if not is_authorized:
            return self.build_response("error", "Only recruiters or founders are authorized to contact candidates.", {}, status.HTTP_403_FORBIDDEN)

        target_user_id = request.data.get("target_user_id")
        message_content = request.data.get("message")
        send_email = request.data.get("send_email", False)

        if not target_user_id or not message_content:
            return self.build_response(
                "error",
                "Target user ID and message are required.",
                {},
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            target_user = CustomUser.objects.get(id=target_user_id)
        except (CustomUser.DoesNotExist, ValueError):
            return self.build_response(
                "error", "User not found.", {}, status.HTTP_404_NOT_FOUND
            )

        # 2. Send Chat Message
        # Check if a direct-type 1-to-1 room already exists between these two users
        room = (
            ChatRoom.objects.filter(
                is_group=False,
                room_type=ChatRoom.ROOM_TYPE_DIRECT,
                participants=request.user,
            )
            .filter(participants=target_user)
            .first()
        )

        if not room:
            room = ChatRoom.objects.create(
                is_group=False, room_type=ChatRoom.ROOM_TYPE_DIRECT
            )
            room.participants.add(request.user, target_user)

        ChatMessage.objects.create(room=room, sender=request.user, text=message_content)
        room.save()  # bump updated_at

        # 3. Send Email
        if send_email:
            try:
                # Fetch recruiter's company profile/name dynamically
                company_name = "Company"
                try:
                    if hasattr(request.user, "company_profile") and request.user.company_profile:
                        company_name = request.user.company_profile.company_name
                    elif hasattr(request.user, "employee_profile") and request.user.employee_profile:
                        emp = request.user.employee_profile
                        if emp.startup:
                            company_name = emp.startup.name
                        elif emp.organization:
                            company_name = emp.organization.name
                except Exception:
                    pass

                subject = (
                    f"Message from {request.user.first_name or 'a Recruiter'} via {company_name}"
                )

                # Render premium direct message HTML template
                context = {
                    "candidate_name": target_user.first_name if target_user.first_name else "Professional",
                    "recruiter_name": request.user.first_name or "a Recruiter",
                    "company_name": company_name,
                    "message_content": message_content,
                    "portal_url": getattr(settings, "FRONTEND_URL", "http://localhost:3000"),
                }
                html_body = render_to_string("emails/direct_message.html", context)

                from useraccounts.tasks import send_notification_email_async
                from_email = getattr(settings, "NOTIFICATION_DEFAULT_FROM_EMAIL", "lakkavaramlinus@gmail.com")

                send_notification_email_async.delay(
                    subject,
                    message_content,
                    [target_user.email],
                    from_email=from_email,
                    html_message=html_body,
                )
            except Exception as e:
                # We still return success for the chat message even if email fails
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Email sending failed: {e}")

        return self.build_response(
            "success", "Message sent successfully.", {}, status.HTTP_200_OK
        )


class RecruiterBulkContactView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        # 1. Authorization check: Only recruiters or staff can bulk contact candidates
        is_authorized = (
            request.user.is_staff or 
            request.user.role in [
                CustomUser.ROLE_ADMIN,
                CustomUser.ROLE_FOUNDER,
                CustomUser.ROLE_CO_FOUNDER,
                CustomUser.ROLE_INVESTOR,
            ] or 
            hasattr(request.user, 'employee_profile')
        )
        if not is_authorized:
            return self.build_response("error", "Only recruiters or founders are authorized to bulk contact candidates.", {}, status.HTTP_403_FORBIDDEN)

        target_user_ids = request.data.get("target_user_ids", [])
        message_content = request.data.get("message")

        if not target_user_ids or not isinstance(target_user_ids, list) or not message_content:
            return self.build_response(
                "error",
                "Target user IDs (list) and message are required.",
                {},
                status.HTTP_400_BAD_REQUEST,
            )

        from django.db import transaction
        success_count = 0
        failed_count = 0

        try:
            with transaction.atomic():
                # 2. Bulk fetch targets to solve N+1
                targets = CustomUser.objects.filter(id__in=target_user_ids)
                targets_by_id = {str(t.id): t for t in targets}
                
                # 3. Bulk fetch existing direct rooms of the user to solve M2M query inside loop
                existing_rooms = ChatRoom.objects.filter(
                    is_group=False,
                    room_type=ChatRoom.ROOM_TYPE_DIRECT,
                    participants=request.user
                ).prefetch_related('participants')
                
                room_by_participant = {}
                for r in existing_rooms:
                    for p in r.participants.all():
                        if p != request.user:
                            room_by_participant[str(p.id)] = r

                chat_messages_to_create = []
                rooms_to_save = []
                
                for target_id in target_user_ids:
                    target_user = targets_by_id.get(str(target_id))
                    if not target_user:
                        failed_count += 1
                        continue

                    room = room_by_participant.get(str(target_user.id))
                    if not room:
                        room = ChatRoom.objects.create(
                            is_group=False, room_type=ChatRoom.ROOM_TYPE_DIRECT
                        )
                        room.participants.add(request.user, target_user)
                        # Keep cache updated
                        room_by_participant[str(target_user.id)] = room

                    chat_messages_to_create.append(
                        ChatMessage(room=room, sender=request.user, text=message_content)
                    )
                    rooms_to_save.append(room)
                    success_count += 1

                # Bulk create all messages at once
                if chat_messages_to_create:
                    ChatMessage.objects.bulk_create(chat_messages_to_create)

                # Bump updated_at timestamps on active rooms
                for r in set(rooms_to_save):
                    r.save()

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Bulk contact transaction failed")
            return self.build_response(
                "error", f"Transaction failed: {str(e)}", {}, status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return self.build_response(
            "success",
            f"Messages sent successfully. Success: {success_count}, Failed: {failed_count}",
            {},
            status.HTTP_200_OK
        )


from maincore.throttling import OTPRequestThrottle, OTPVerifyThrottle

class RequestOTPView(APIView, RequestResponseMixin):
    permission_classes = (AllowAny,)
    throttle_classes = [OTPRequestThrottle]

    def post(self, request, *args, **kwargs):
        email = request.data.get("email")
        if not email:
            return self.build_response("error", "Email is required.", {}, status.HTTP_400_BAD_REQUEST)
        
        try:
            user = CustomUser.objects.get(email=email)
            if EmailService.send_otp_email(user):
                return self.build_response("success", "OTP sent to your email.", {}, status.HTTP_200_OK)
            return self.build_response("error", "Failed to send email. Please try again later.", {}, status.HTTP_500_INTERNAL_SERVER_ERROR)
        except CustomUser.DoesNotExist:
            return self.build_response("error", "User with this email does not exist.", {}, status.HTTP_404_NOT_FOUND)


class VerifyOTPView(APIView, RequestResponseMixin):
    permission_classes = (AllowAny,)
    throttle_classes = [OTPVerifyThrottle]

    def post(self, request, *args, **kwargs):
        email = request.data.get("email")
        otp = request.data.get("otp")
        
        if not email or not otp:
            return self.build_response("error", "Email and OTP are required.", {}, status.HTTP_400_BAD_REQUEST)
            
        try:
            user = CustomUser.objects.get(email=email)
            success, message = EmailService.verify_otp(user, otp)
            
            if success:
                tokens = UserService.generate_tokens(user)
                response = self.build_response(
                    status_msg="success",
                    message="Verification successful.",
                    data={"user": UserSerializer(user).data},
                    status_code=status.HTTP_200_OK,
                )
                _set_auth_cookies(response, tokens["access"], tokens["refresh"])
                return response
            return self.build_response("error", message, {}, status.HTTP_400_BAD_REQUEST)
        except CustomUser.DoesNotExist:
            return self.build_response("error", "User not found.", {}, status.HTTP_404_NOT_FOUND)


class Request2FAOTPsView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        user = request.user
        secondary_email = request.data.get("secondary_email")
        third_email = request.data.get("third_email")

        if not secondary_email or not third_email:
            return self.build_response("error", "Both secondary and third emails are required.", {}, status.HTTP_400_BAD_REQUEST)

        # Basic validation
        if secondary_email == user.email or third_email == user.email:
            return self.build_response("error", "Backup emails cannot be the same as your primary account email.", {}, status.HTTP_400_BAD_REQUEST)

        if secondary_email == third_email:
            return self.build_response("error", "Secondary and third emails must be different.", {}, status.HTTP_400_BAD_REQUEST)

        if EmailService.send_2fa_otp_emails(user, secondary_email, third_email):
            return self.build_response("success", "OTP verification codes have been sent to both backup emails.", {}, status.HTTP_200_OK)
        
        return self.build_response("error", "Failed to send verification emails. Please check inputs and try again.", {}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class Verify2FAOTPsView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        user = request.user
        secondary_otp = request.data.get("secondary_otp")
        third_otp = request.data.get("third_otp")

        if not secondary_otp or not third_otp:
            return self.build_response("error", "Both OTP codes are required for verification.", {}, status.HTTP_400_BAD_REQUEST)

        # Verify secondary email OTP (timing-safe)
        import hmac
        if not user.secondary_email_otp or not hmac.compare_digest(str(user.secondary_email_otp), str(secondary_otp)):
            return self.build_response("error", "Invalid secondary email verification code.", {}, status.HTTP_400_BAD_REQUEST)

        if user.secondary_email_otp_created_at:
            expiration = user.secondary_email_otp_created_at + timezone.timedelta(minutes=10)
            if timezone.now() > expiration:
                return self.build_response("error", "Secondary email verification code has expired.", {}, status.HTTP_400_BAD_REQUEST)

        # Verify third email OTP (timing-safe)
        if not user.third_email_otp or not hmac.compare_digest(str(user.third_email_otp), str(third_otp)):
            return self.build_response("error", "Invalid third email verification code.", {}, status.HTTP_400_BAD_REQUEST)

        if user.third_email_otp_created_at:
            expiration = user.third_email_otp_created_at + timezone.timedelta(minutes=10)
            if timezone.now() > expiration:
                return self.build_response("error", "Third email verification code has expired.", {}, status.HTTP_400_BAD_REQUEST)

        # Mark 2FA enabled
        user.is_2fa_enabled = True
        user.secondary_email_otp = None
        user.third_email_otp = None
        user.secondary_email_otp_created_at = None
        user.third_email_otp_created_at = None
        user.save()

        return self.build_response(
            "success",
            "Two-step verification activated successfully.",
            UserSerializer(user).data,
            status.HTTP_200_OK
        )


class Disable2FAView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        user = request.user
        user.is_2fa_enabled = False
        user.secondary_email = None
        user.third_email = None
        user.secondary_email_otp = None
        user.third_email_otp = None
        user.secondary_email_otp_created_at = None
        user.third_email_otp_created_at = None
        user.save()

        return self.build_response(
            "success",
            "Two-step verification has been disabled.",
            UserSerializer(user).data,
            status.HTTP_200_OK
        )


class RequestSecondary2FAOTPView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        user = request.user
        secondary_email = request.data.get("secondary_email")

        if not secondary_email:
            return self.build_response("error", "Secondary email is required.", {}, status.HTTP_400_BAD_REQUEST)

        if secondary_email == user.email:
            return self.build_response("error", "Backup email cannot be the same as your primary account email.", {}, status.HTTP_400_BAD_REQUEST)

        if EmailService.send_secondary_2fa_otp(user, secondary_email):
            return self.build_response("success", "OTP verification code has been sent to your secondary email.", {}, status.HTTP_200_OK)
        
        return self.build_response("error", "Failed to send verification email. Please try again.", {}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifySecondary2FAOTPView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        user = request.user
        secondary_otp = request.data.get("secondary_otp")

        if not secondary_otp:
            return self.build_response("error", "OTP code is required for verification.", {}, status.HTTP_400_BAD_REQUEST)

        if not user.secondary_email_otp or user.secondary_email_otp != secondary_otp:
            return self.build_response("error", "Invalid secondary email verification code.", {}, status.HTTP_400_BAD_REQUEST)

        if user.secondary_email_otp_created_at:
            expiration = user.secondary_email_otp_created_at + timezone.timedelta(minutes=10)
            if timezone.now() > expiration:
                return self.build_response("error", "Verification code has expired.", {}, status.HTTP_400_BAD_REQUEST)

        # Mark secondary email OTP as VERIFIED
        user.secondary_email_otp = 'DONE'
        user.save(update_fields=['secondary_email_otp'])

        return self.build_response(
            "success",
            "Secondary backup email verified successfully.",
            {},
            status.HTTP_200_OK
        )


class RequestThird2FAOTPView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        user = request.user
        third_email = request.data.get("third_email")

        if not third_email:
            return self.build_response("error", "Third email is required.", {}, status.HTTP_400_BAD_REQUEST)

        if third_email == user.email:
            return self.build_response("error", "Backup email cannot be the same as your primary account email.", {}, status.HTTP_400_BAD_REQUEST)

        if third_email == user.secondary_email:
            return self.build_response("error", "Third email must be different from secondary email.", {}, status.HTTP_400_BAD_REQUEST)

        # Check if secondary email is already verified
        if user.secondary_email_otp != 'DONE':
            return self.build_response("error", "Please verify your secondary backup email first.", {}, status.HTTP_400_BAD_REQUEST)

        if EmailService.send_third_2fa_otp(user, third_email):
            return self.build_response("success", "OTP verification code has been sent to your third email.", {}, status.HTTP_200_OK)
        
        return self.build_response("error", "Failed to send verification email. Please try again.", {}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyThird2FAOTPView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        user = request.user
        third_otp = request.data.get("third_otp")

        if not third_otp:
            return self.build_response("error", "OTP code is required for verification.", {}, status.HTTP_400_BAD_REQUEST)

        # Check if secondary email is already verified
        if user.secondary_email_otp != 'DONE':
            return self.build_response("error", "Please verify your secondary backup email first.", {}, status.HTTP_400_BAD_REQUEST)

        if not user.third_email_otp or user.third_email_otp != third_otp:
            return self.build_response("error", "Invalid third email verification code.", {}, status.HTTP_400_BAD_REQUEST)

        if user.third_email_otp_created_at:
            expiration = user.third_email_otp_created_at + timezone.timedelta(minutes=10)
            if timezone.now() > expiration:
                return self.build_response("error", "Verification code has expired.", {}, status.HTTP_400_BAD_REQUEST)

        # Enable 2FA
        user.is_2fa_enabled = True
        user.secondary_email_otp = None
        user.third_email_otp = None
        user.secondary_email_otp_created_at = None
        user.third_email_otp_created_at = None
        user.save()

        return self.build_response(
            "success",
            "Two-step verification activated successfully.",
            UserSerializer(user).data,
            status.HTTP_200_OK
        )



