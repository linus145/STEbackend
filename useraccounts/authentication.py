from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.conf import settings

class CookieJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that reads the access token from HttpOnly cookies.
    Isolates employee sessions cleanly by supporting both tokens.
    """

    def authenticate(self, request):
        # 1. Try reading the employee-specific cookie first
        raw_token = request.COOKIES.get("employee_access_token")

        # 2. Fallback to the standard user cookie if employee cookie is not set
        if raw_token is None:
            raw_token = request.COOKIES.get(
                settings.SIMPLE_JWT.get('AUTH_COOKIE', 'access_token')
            )

        # 3. Fallback to Authorization header if no cookie is present
        if raw_token is None:
            header = self.get_header(request)
            if header is None:
                return None
            raw_token = self.get_raw_token(header)

        if raw_token is None:
            return None

        try:
            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)
        except Exception as e:
            raise AuthenticationFailed(str(e))
        
        # Enforce employee profile verification if authenticated via employee cookie
        if request.COOKIES.get("employee_access_token") == raw_token:
            from employees.models import Employee
            try:
                # Just verify the relation exists
                employee = user.employee_profile
            except (AttributeError, Employee.DoesNotExist):
                raise AuthenticationFailed("This account is not registered as an employee.")

        return user, validated_token
