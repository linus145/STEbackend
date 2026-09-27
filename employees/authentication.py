from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings
from rest_framework.exceptions import AuthenticationFailed
from django.conf import settings

class EmployeeCookieJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication for the Employee Portal.
    Strictly reads the access token from the employee-isolated cookie 'employee_access_token'.
    Ensures that the authenticated user possesses an active employee profile.
    """

    def get_user(self, validated_token):
        user_id = validated_token.get(api_settings.USER_ID_CLAIM)
        from employees.models import EmployeeUser
        try:
            emp_user = EmployeeUser.objects.select_related('employee').get(id=user_id)
            if not emp_user.is_active:
                raise AuthenticationFailed("Employee user account is inactive.", code="user_inactive")
            return emp_user
        except EmployeeUser.DoesNotExist:
            return super().get_user(validated_token)

    def authenticate(self, request):
        # Strictly read from the employee-specific cookie
        raw_token = request.COOKIES.get("employee_access_token")

        if raw_token is None:
            # Fallback to Authorization header
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
        
        # Enforce that the user possesses a linked Employee profile
        employee = getattr(user, 'employee_profile', None)
        if not employee:
            raise AuthenticationFailed("This account is not registered as an employee.")

        return user, validated_token
