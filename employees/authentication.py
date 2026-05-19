from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.conf import settings
from employees.models import Employee

class EmployeeCookieJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication for the Employee Portal.
    Strictly reads the access token from the employee-isolated cookie 'employee_access_token'.
    Ensures that the authenticated user possesses an active employee profile.
    """

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
        try:
            employee = user.employee_profile
        except (AttributeError, Employee.DoesNotExist):
            raise AuthenticationFailed("This account is not registered as an employee.")

        return user, validated_token
