from rest_framework_simplejwt.authentication import JWTAuthentication
from django.conf import settings


class CookieJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that reads the access token from HttpOnly cookies.
    Falls back to Authorization header if cookie is not present.
    """

    def authenticate(self, request):
        # First try reading from the cookie
        raw_token = request.COOKIES.get(
            settings.SIMPLE_JWT.get('AUTH_COOKIE', 'access_token')
        )

        # Fallback to Authorization header
        if raw_token is None:
            header = self.get_header(request)
            if header is None:
                return None
            raw_token = self.get_raw_token(header)

        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
