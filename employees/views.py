from rest_framework import viewsets, filters, permissions, status
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from employees.models import (
    Employee,
    EmployeeProfile,
    EmergencyContact,
    EmployeeDocument,
)
from employees.serializers import (
    EmployeeSerializer,
    EmployeeDetailSerializer,
    EmployeeProfileSerializer,
    EmergencyContactSerializer,
    EmployeeDocumentSerializer,
)
from organization.views import StartupTenantMixin

from rest_framework.decorators import action


class EmployeeViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Employee.objects.select_related(
        "department", "designation", "user", "profile_details"
    ).all()
    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # 1. Retrieve the base tenant-scoped queryset from StartupTenantMixin
        queryset = super().get_queryset()

        # 2. Package query parameters
        filters = {
            "search": self.request.query_params.get("search"),
            "status": self.request.query_params.get("status"),
            "employment_type": self.request.query_params.get("employment_type"),
            "department": self.request.query_params.get("department"),
            "designation": self.request.query_params.get("designation"),
            "joining_date__gte": self.request.query_params.get("joining_date__gte"),
            "joining_date__lte": self.request.query_params.get("joining_date__lte"),
            "ordering": self.request.query_params.get("ordering"),
        }

        from searchfilters.services import SearchService

        # 3. Delegate filtering completely to the searchfilters service module
        return SearchService.filter_employees(queryset, filters)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return EmployeeDetailSerializer
        return EmployeeSerializer

    def perform_create(self, serializer):
        user = self.request.user
        startup = user.startups.first()

        # Exact match of StartupTenantMixin logic for visibility
        from organization.models import Organization

        company = getattr(user, "company_profile", None)
        organization = None
        if company:
            organization = Organization.objects.filter(company=company).first()
            if not organization:
                organization = Organization.objects.create(
                    company=company, name=company.company_name
                )

        # Default joining date to today for immediate visibility
        from django.utils import timezone

        joining_date = (
            serializer.validated_data.get("joining_date") or timezone.now().date()
        )

        serializer.save(
            startup=startup, organization=organization, joining_date=joining_date
        )

    @action(detail=False, methods=["post"], url_path="add-manual")
    def add_manual(self, request):
        data = request.data.copy()
        if "employee_id" not in data or not data["employee_id"]:
            data["employee_id"] = "TEMP-ID"

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    @action(detail=True, methods=["post"], url_path="send-credentials")
    def send_credentials(self, request, pk=None):
        employee = self.get_object()
        from employees.services import EmployeeService

        result = EmployeeService.send_credentials_email(
            employee, request.META.get("HTTP_HOST"), request.build_absolute_uri
        )
        return Response(
            {"message": "Credentials email processed successfully.", **result},
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="change-credentials",
        permission_classes=[permissions.IsAuthenticated],
    )
    def change_credentials(self, request):
        user = request.user
        try:
            employee = user.employee_profile
        except Employee.DoesNotExist:
            return Response(
                {"error": "Employee profile not found for this user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        from employees.services import EmployeeService

        try:
            portal_username = EmployeeService.change_credentials(
                employee,
                user,
                request.data.get("portal_username"),
                request.data.get("password"),
            )
            return Response(
                {
                    "message": "Credentials updated successfully.",
                    "portal_username": portal_username,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            msg = getattr(e, "detail", None) or str(e)
            if isinstance(msg, list) and len(msg) > 0:
                msg = msg[0]
            return Response({"error": str(msg)}, status=status.HTTP_400_BAD_REQUEST)


class EmergencyContactViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = EmergencyContact.objects.all()
    serializer_class = EmergencyContactSerializer
    permission_classes = [permissions.IsAuthenticated]


class EmployeeDocumentViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = EmployeeDocument.objects.all()
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]


def _set_employee_auth_cookies(response, access_token, refresh_token):
    """Centralized cookie setter for Employee Portal — isolates sessions completely."""
    jwt_settings = settings.SIMPLE_JWT
    response.set_cookie(
        key="employee_access_token",
        value=access_token,
        expires=jwt_settings["ACCESS_TOKEN_LIFETIME"],
        secure=jwt_settings["AUTH_COOKIE_SECURE"],
        httponly=jwt_settings["AUTH_COOKIE_HTTP_ONLY"],
        samesite=jwt_settings["AUTH_COOKIE_SAMESITE"],
        path=jwt_settings.get("AUTH_COOKIE_PATH", "/"),
    )
    response.set_cookie(
        key="employee_refresh_token",
        value=refresh_token,
        expires=jwt_settings["REFRESH_TOKEN_LIFETIME"],
        secure=jwt_settings["AUTH_COOKIE_SECURE"],
        httponly=jwt_settings["AUTH_COOKIE_HTTP_ONLY"],
        samesite=jwt_settings["AUTH_COOKIE_SAMESITE"],
        path=jwt_settings.get("AUTH_COOKIE_PATH", "/"),
    )
    return response


def _delete_employee_auth_cookies(response):
    """Centralized cookie deletion for Employee Portal."""
    jwt_settings = settings.SIMPLE_JWT
    response.delete_cookie(
        "employee_access_token",
        path=jwt_settings.get("AUTH_COOKIE_PATH", "/"),
    )
    response.delete_cookie(
        "employee_refresh_token",
        path=jwt_settings.get("AUTH_COOKIE_PATH", "/"),
    )
    return response


from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.conf import settings
from useraccounts.services import UserService
from useraccounts.serializers import UserSerializer


class EmployeeLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        username_or_email = request.data.get("email") or request.data.get("username")
        password = request.data.get("password")

        if not username_or_email or not password:
            return Response(
                {"error": "Username/Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from employees.services import EmployeeService

        try:
            user, tokens = EmployeeService.authenticate_employee(
                username_or_email, password
            )
            response = Response(
                {
                    "status": "success",
                    "message": "Employee login successful.",
                    "data": {"user": UserSerializer(user).data},
                },
                status=status.HTTP_200_OK,
            )

            _set_employee_auth_cookies(response, tokens["access"], tokens["refresh"])
            return response
        except Exception as e:
            error_data = getattr(e, "detail", None)
            if isinstance(error_data, dict):
                return Response(error_data, status=status.HTTP_403_FORBIDDEN)
            msg = error_data or str(e)
            if isinstance(msg, list) and len(msg) > 0:
                msg = msg[0]
            return Response({"error": str(msg)}, status=status.HTTP_401_UNAUTHORIZED)


class EmployeeLogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = Response(
            {"status": "success", "message": "Employee logged out successfully."},
            status=status.HTTP_200_OK,
        )
        _delete_employee_auth_cookies(response)
        return response
