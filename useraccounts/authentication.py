from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings
from rest_framework.exceptions import AuthenticationFailed
from django.conf import settings

class CookieJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that reads the access token from HttpOnly cookies.
    Isolates employee sessions cleanly by supporting both tokens.
    """

    def get_user(self, validated_token):
        user_type = validated_token.get("user_type")
        user_id = validated_token.get(api_settings.USER_ID_CLAIM)

        if user_type == "employee":
            from employees.models import EmployeeUser
            try:
                emp_user = EmployeeUser.objects.select_related('employee').get(id=user_id)
                if not emp_user.is_active:
                    raise AuthenticationFailed("Employee user account is inactive.", code="user_inactive")
                return emp_user
            except EmployeeUser.DoesNotExist:
                raise AuthenticationFailed("Employee user not found.", code="user_not_found")

        try:
            return super().get_user(validated_token)
        except AuthenticationFailed:
            # Fallback for employee tokens missing user_type claim
            from employees.models import EmployeeUser
            try:
                emp_user = EmployeeUser.objects.select_related('employee').get(id=user_id)
                if not emp_user.is_active:
                    raise AuthenticationFailed("Employee user account is inactive.", code="user_inactive")
                return emp_user
            except EmployeeUser.DoesNotExist:
                raise

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
            employee = getattr(user, 'employee_profile', None)
            if not employee:
                raise AuthenticationFailed("This account is not registered as an employee.")

        return user, validated_token
