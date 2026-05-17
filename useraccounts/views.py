from django.db import models
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated

from django.conf import settings
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
    LogoutSerializer,
)
from founders.serializers import FounderUpdateSerializer
from investors.serializers import InvestorUpdateSerializer
from .services import UserService
from google.oauth2 import id_token
from google.auth.transport import requests
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import redirect
from django.core.mail import send_mail
from .models import CustomUser


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


class LoginView(APIView, RequestResponseMixin):
    permission_classes = (AllowAny,)

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
        user_fields = ["first_name", "last_name", "phone_number"]
        user_data = {k: v for k, v in data.items() if k in user_fields}
        profile_data = {k: v for k, v in data.items() if k not in user_fields}

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
            from maincore.imagekit_utils import ImageKitService

            profile_obj = None
            if user.role == user.ROLE_FOUNDER:
                if not hasattr(user, "founder_profile"):
                    from founders.models import Founder

                    Founder.objects.create(user=user)
                profile_obj = user.founder_profile
                profile_serializer = FounderUpdateSerializer(
                    profile_obj, data=profile_data, partial=True
                )
            elif user.role == user.ROLE_INVESTOR:
                if not hasattr(user, "investor_profile"):
                    from investors.models import Investor

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
            return response

        access_token = serializer.validated_data.get("access")
        refresh_token_new = serializer.validated_data.get("refresh")

        response = Response(
            {"status": "success", "message": "Tokens refreshed"},
            status=status.HTTP_200_OK,
        )

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
        from .models import WsTicket

        ticket = WsTicket.objects.create(user=request.user)
        return Response({"token": str(ticket.id)}, status=status.HTTP_200_OK)


class PublicProfileView(APIView, RequestResponseMixin):
    permission_classes = (AllowAny,)

    def get(self, request, user_id, *args, **kwargs):
        from .models import CustomUser

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
        from .serializers import ChangePasswordSerializer

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
        from .serializers import UpdatePhoneNumberSerializer

        user = request.user
        serializer = UpdatePhoneNumberSerializer(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data.get("phone_number")

            # Check if this phone number is already registered to another user
            from django.contrib.auth import get_user_model

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

    def post(self, request, *args, **kwargs):
        # In redirect mode, Google sends data as form-data
        token = request.data.get("credential") or request.POST.get("credential")

        if not token:
            print("DEBUG: No credential found in request")
            return redirect(f"{settings.FRONTEND_URL}/login?error=no_token")

        try:
            print(f"DEBUG: Verifying Google Token...")
            idinfo = id_token.verify_oauth2_token(
                token, requests.Request(), settings.GOOGLE_OAUTH_CLIENT_ID
            )

            google_id = idinfo["sub"]
            email = idinfo["email"]
            print(f"DEBUG: Google User Verified: {email}")

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
            print(f"DEBUG: Token verification failed: {str(e)}")
            return redirect(f"{settings.FRONTEND_URL}/login?error=invalid_token")
        except Exception as e:
            print(f"DEBUG: Google Login Exception: {str(e)}")
            return redirect(f"{settings.FRONTEND_URL}/login?error=server_error")


class UserListView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        # Exclude Admin and Staff users to show all potential candidates
        users = CustomUser.objects.exclude(
            models.Q(role=CustomUser.ROLE_ADMIN) | models.Q(is_staff=True)
        )
        serializer = UserSerializer(users, many=True)
        return self.build_response(
            "success",
            "Users fetched successfully.",
            serializer.data,
            status.HTTP_200_OK,
        )


class RecruiterContactView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
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

        # 1. Send Chat Message
        from chat.models import ChatRoom, Message as ChatMessage
        from django.db.models import Count

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

        # 2. Send Email
        if send_email:
            try:
                from django.template.loader import render_to_string
                from django.core.mail import get_connection

                subject = (
                    f"Message from {request.user.first_name or 'a Recruiter'} via B2LINQ"
                )

                # Fetch recruiter's company profile
                company_name = "B2LINQ Partner"
                try:
                    from startups.models import CompanyProfile
                    company = CompanyProfile.objects.get(owner=request.user)
                    if company.name:
                        company_name = company.name
                except Exception:
                    pass

                # Render premium direct message HTML template
                context = {
                    "candidate_name": target_user.first_name if target_user.first_name else "Professional",
                    "recruiter_name": request.user.first_name or "a Recruiter",
                    "company_name": company_name,
                    "message_content": message_content,
                    "portal_url": getattr(settings, "FRONTEND_URL", "http://localhost:3000"),
                }
                html_body = render_to_string("AIrounds/emails/direct_message.html", context)

                # Dynamically fetch the notification connection settings
                backend = getattr(settings, "NOTIFICATION_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
                host = getattr(settings, "NOTIFICATION_EMAIL_HOST", "smtp-relay.brevo.com")
                port = int(getattr(settings, "NOTIFICATION_EMAIL_PORT", 587))
                username = getattr(settings, "NOTIFICATION_EMAIL_HOST_USER", "")
                password = getattr(settings, "NOTIFICATION_EMAIL_HOST_PASSWORD", "")
                use_tls = getattr(settings, "NOTIFICATION_EMAIL_USE_TLS", True)
                from_email = getattr(settings, "NOTIFICATION_DEFAULT_FROM_EMAIL", "lakkavaramlinus@gmail.com")

                connection = get_connection(
                    backend=backend,
                    host=host,
                    port=port,
                    username=username,
                    password=password,
                    use_tls=use_tls,
                )

                send_mail(
                    subject,
                    message_content,
                    from_email,
                    [target_user.email],
                    fail_silently=False,
                    connection=connection,
                    html_message=html_body,
                )
            except Exception as e:
                # We still return success for the chat message even if email fails
                print(f"Email sending failed: {e}")

        return self.build_response(
            "success", "Message sent successfully.", {}, status.HTTP_200_OK
        )


class RecruiterBulkContactView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        target_user_ids = request.data.get("target_user_ids", [])
        message_content = request.data.get("message")

        if not target_user_ids or not isinstance(target_user_ids, list) or not message_content:
            return self.build_response(
                "error",
                "Target user IDs (list) and message are required.",
                {},
                status.HTTP_400_BAD_REQUEST,
            )

        from chat.models import ChatRoom, Message as ChatMessage
        
        success_count = 0
        failed_count = 0

        for target_user_id in target_user_ids:
            try:
                target_user = CustomUser.objects.get(id=target_user_id)
            except (CustomUser.DoesNotExist, ValueError):
                failed_count += 1
                continue

            # 1. Send Chat Message
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
            
            success_count += 1

        return self.build_response(
            "success",
            f"Messages sent successfully. Success: {success_count}, Failed: {failed_count}",
            {},
            status.HTTP_200_OK
        )


class RequestOTPView(APIView, RequestResponseMixin):
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        from .email_service import EmailService
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

    def post(self, request, *args, **kwargs):
        from .email_service import EmailService
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


