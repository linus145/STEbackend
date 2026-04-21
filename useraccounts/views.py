from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated

from django.conf import settings
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken
from .serializers import RegisterSerializer, LoginSerializer, UserSerializer, LogoutSerializer
from founders.serializers import FounderUpdateSerializer
from investors.serializers import InvestorUpdateSerializer
from .services import UserService

class RequestResponseMixin:
    """Helper to maintain standardized structured JSON output globally"""
    def build_response(self, status_msg: str, message: str, data: dict = None, status_code: int = status.HTTP_200_OK):
        payload = {
            "status": status_msg,
            "message": message,
            "data": data if data else {}
        }
        return Response(payload, status=status_code)


def _set_auth_cookies(response, access_token, refresh_token):
    """Centralized cookie setter — ensures consistent cookie config everywhere."""
    jwt_settings = settings.SIMPLE_JWT
    response.set_cookie(
        key=jwt_settings['AUTH_COOKIE'],
        value=access_token,
        expires=jwt_settings['ACCESS_TOKEN_LIFETIME'],
        secure=jwt_settings['AUTH_COOKIE_SECURE'],
        httponly=jwt_settings['AUTH_COOKIE_HTTP_ONLY'],
        samesite=jwt_settings['AUTH_COOKIE_SAMESITE'],
        path=jwt_settings.get('AUTH_COOKIE_PATH', '/'),
    )
    response.set_cookie(
        key=jwt_settings['AUTH_COOKIE_REFRESH'],
        value=refresh_token,
        expires=jwt_settings['REFRESH_TOKEN_LIFETIME'],
        secure=jwt_settings['AUTH_COOKIE_SECURE'],
        httponly=jwt_settings['AUTH_COOKIE_HTTP_ONLY'],
        samesite=jwt_settings['AUTH_COOKIE_SAMESITE'],
        path=jwt_settings.get('AUTH_COOKIE_PATH', '/'),
    )
    return response


def _delete_auth_cookies(response):
    """Centralized cookie deletion — ensures consistent cleanup."""
    jwt_settings = settings.SIMPLE_JWT
    response.delete_cookie(
        jwt_settings['AUTH_COOKIE'],
        path=jwt_settings.get('AUTH_COOKIE_PATH', '/'),
    )
    response.delete_cookie(
        jwt_settings['AUTH_COOKIE_REFRESH'],
        path=jwt_settings.get('AUTH_COOKIE_PATH', '/'),
    )
    return response


class RegisterView(APIView, RequestResponseMixin):
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = UserService.create_user(serializer.validated_data)
            tokens = UserService.generate_tokens(user)
            user_data = UserSerializer(user).data
            response = self.build_response(
                status_msg="success",
                message="User registered successfully.",
                data={"user": user_data},
                status_code=status.HTTP_201_CREATED
            )
            _set_auth_cookies(response, tokens['access'], tokens['refresh'])
            return response
        return self.build_response("error", "Validation failed", serializer.errors, status.HTTP_400_BAD_REQUEST)


class LoginView(APIView, RequestResponseMixin):
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            user = UserService.authenticate_user(email, password)
            if user:
                tokens = UserService.generate_tokens(user)
                response = self.build_response(
                    status_msg="success",
                    message="Login successful.",
                    data={"user": UserSerializer(user).data},
                    status_code=status.HTTP_200_OK
                )
                _set_auth_cookies(response, tokens['access'], tokens['refresh'])
                return response
            return self.build_response("error", "Invalid credentials.", {}, status.HTTP_401_UNAUTHORIZED)
        return self.build_response("error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView, RequestResponseMixin):
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get(settings.SIMPLE_JWT.get('AUTH_COOKIE_REFRESH', 'refresh_token'))
        if refresh_token:
            UserService.logout_user(refresh_token)
        
        response = self.build_response("success", "Logged out successfully.", {}, status.HTTP_200_OK)
        _delete_auth_cookies(response)
        return response


class ProfileView(APIView, RequestResponseMixin):
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        serializer = UserSerializer(request.user)
        return self.build_response("success", "Profile fetched successfully.", serializer.data, status.HTTP_200_OK)

    def patch(self, request, *args, **kwargs):
        user = request.user
        data = request.data
        
        # Split data into user fields and profile fields
        user_fields = ['first_name', 'last_name', 'phone_number']
        user_data = {k: v for k, v in data.items() if k in user_fields}
        profile_data = {k: v for k, v in data.items() if k not in user_fields}
        
        # Update User
        if user_data:
            user_serializer = UserSerializer(user, data=user_data, partial=True)
            if user_serializer.is_valid():
                user_serializer.save()
            else:
                return self.build_response("error", "User validation failed", user_serializer.errors, status.HTTP_400_BAD_REQUEST)
        
        # Update Profile
        if profile_data:
            if user.role == user.ROLE_FOUNDER:
                if not hasattr(user, 'founder_profile'):
                    from founders.models import Founder
                    Founder.objects.create(user=user)
                profile_serializer = FounderUpdateSerializer(user.founder_profile, data=profile_data, partial=True)
            elif user.role == user.ROLE_INVESTOR:
                if not hasattr(user, 'investor_profile'):
                    from investors.models import Investor
                    Investor.objects.create(user=user)
                profile_serializer = InvestorUpdateSerializer(user.investor_profile, data=profile_data, partial=True)
            else:
                return self.build_response("error", "Invalid user role for profile update", {}, status.HTTP_400_BAD_REQUEST)

            if profile_serializer.is_valid():
                profile_serializer.save()
            else:
                return self.build_response("error", "Profile validation failed", profile_serializer.errors, status.HTTP_400_BAD_REQUEST)
        
        return self.build_response("success", "Profile updated successfully.", UserSerializer(user).data, status.HTTP_200_OK)

class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get(settings.SIMPLE_JWT.get('AUTH_COOKIE_REFRESH', 'refresh_token'))
        
        if not refresh_token:
            # No refresh cookie → controlled 401, no crash
            response = Response(
                {"detail": "No refresh token provided", "code": "token_missing"},
                status=status.HTTP_401_UNAUTHORIZED
            )
            _delete_auth_cookies(response)
            return response
        
        # Safely copy request data natively to avoid immutability issues
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        data['refresh'] = refresh_token
            
        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            response = Response(
                {"detail": "Token is invalid or expired", "code": "token_not_valid"},
                status=status.HTTP_401_UNAUTHORIZED
            )
            _delete_auth_cookies(response)
            return response
            
        access_token = serializer.validated_data.get('access')
        refresh_token_new = serializer.validated_data.get('refresh')
        
        response = Response(
            {"status": "success", "message": "Tokens refreshed"},
            status=status.HTTP_200_OK
        )
        
        jwt_settings = settings.SIMPLE_JWT
        response.set_cookie(
            key=jwt_settings['AUTH_COOKIE'],
            value=access_token,
            expires=jwt_settings['ACCESS_TOKEN_LIFETIME'],
            secure=jwt_settings['AUTH_COOKIE_SECURE'],
            httponly=jwt_settings['AUTH_COOKIE_HTTP_ONLY'],
            samesite=jwt_settings['AUTH_COOKIE_SAMESITE'],
            path=jwt_settings.get('AUTH_COOKIE_PATH', '/'),
        )
        
        if refresh_token_new:
            response.set_cookie(
                key=jwt_settings['AUTH_COOKIE_REFRESH'],
                value=refresh_token_new,
                expires=jwt_settings['REFRESH_TOKEN_LIFETIME'],
                secure=jwt_settings['AUTH_COOKIE_SECURE'],
                httponly=jwt_settings['AUTH_COOKIE_HTTP_ONLY'],
                samesite=jwt_settings['AUTH_COOKIE_SAMESITE'],
                path=jwt_settings.get('AUTH_COOKIE_PATH', '/'),
            )
            
        return response


class WsTicketView(APIView):
    """
    Returns the current access token so the frontend can pass it
    as a query parameter when opening a WebSocket connection.
    HTTPOnly cookies are invisible to JavaScript, so this
    authenticated endpoint is the bridge.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        token = request.COOKIES.get(
            settings.SIMPLE_JWT.get('AUTH_COOKIE', 'access_token')
        )
        if not token:
            return Response(
                {"error": "No access token found"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        return Response({"token": token}, status=status.HTTP_200_OK)
