from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from .serializers import (
    StartupSerializer,
    StartupCreateUpdateSerializer,
    CompanyProfileSerializer,
    CompanyHRProfileSerializer,
    CompanyRegisterSerializer,
    CompanyUpdateSerializer,
    CompanyLoginSerializer,
)
from .services import StartupService
from .models import CompanyProfile, CompanyHRProfile
from useraccounts.services import UserService
from useraccounts.serializers import UserSerializer
from django.db import transaction
from django.contrib.auth import get_user_model


class ResponseMixin:
    """Standardized JSON response helper — mirrors useraccounts pattern."""

    def build_response(
        self, status_msg, message, data=None, status_code=status.HTTP_200_OK
    ):
        return Response(
            {"status": status_msg, "message": message, "data": data or {}},
            status=status_code,
        )


# ─── Company Profile Views ─────────────────────────────────────────


class IsCompanyOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.owner == request.user


class CompanyRegisterView(APIView, ResponseMixin):
    """
    POST: Register a new company profile for the authenticated user.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request):
        if request.user.is_authenticated and hasattr(request.user, "company_profile"):
            return self.build_response(
                "error",
                "You already have a registered company.",
                CompanyProfileSerializer(request.user.company_profile).data,
                status.HTTP_400_BAD_REQUEST,
            )

        serializer = CompanyRegisterSerializer(data=request.data)
        if serializer.is_valid():
            company = serializer.save(
                owner=request.user if request.user.is_authenticated else None
            )
            return self.build_response(
                "success",
                "Company registered successfully.",
                CompanyProfileSerializer(company).data,
                status.HTTP_201_CREATED,
            )
        return self.build_response(
            "error",
            "Validation failed.",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST,
        )


class CompanyLoginView(APIView, ResponseMixin):
    """
    POST: Login using company_email and company_password.
    """

    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = CompanyLoginSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            password = serializer.validated_data["password"]

            try:
                company = CompanyProfile.objects.get(company_email=email)
                if company.check_company_password(password):
                    # Ensure company has a linked user for token generation (Shadow User)
                    if not company.owner:
                        user_model = get_user_model()
                        # Create shadow user for company
                        shadow_user = user_model.objects.create_user(
                            email=email,
                            password=None,
                            role="FOUNDER",  # Use FOUNDER role as it's the recruiter role
                            first_name=company.company_name,
                            is_verified=True,
                        )
                        company.owner = shadow_user
                        company.save()

                    user = company.owner
                    tokens = UserService.generate_tokens(user)

                    from useraccounts.views import _set_auth_cookies

                    response = self.build_response(
                        "success",
                        "Company login successful.",
                        {
                            "user": UserSerializer(user).data,
                            "company": CompanyProfileSerializer(company).data,
                        },
                        status.HTTP_200_OK,
                    )
                    _set_auth_cookies(response, tokens["access"], tokens["refresh"])
                    return response

                return self.build_response(
                    "error",
                    "Invalid company credentials.",
                    {},
                    status.HTTP_401_UNAUTHORIZED,
                )
            except CompanyProfile.DoesNotExist:
                return self.build_response(
                    "error", "Company not found.", {}, status.HTTP_404_NOT_FOUND
                )

        return self.build_response(
            "error",
            "Validation failed.",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST,
        )


class CompanyProfileView(APIView, ResponseMixin):
    """
    GET: Retrieve the authenticated user's company profile.
    PATCH: Update the authenticated user's company profile.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not hasattr(request.user, "company_profile"):
            return self.build_response(
                "error", "No company profile found.", {}, status.HTTP_404_NOT_FOUND
            )
        company = request.user.company_profile
        serializer = CompanyProfileSerializer(company)
        return self.build_response(
            "success", "Company profile fetched.", serializer.data
        )

    def patch(self, request):
        if not hasattr(request.user, "company_profile"):
            return self.build_response(
                "error", "No company profile found.", {}, status.HTTP_404_NOT_FOUND
            )
        company = request.user.company_profile
        serializer = CompanyUpdateSerializer(company, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return self.build_response(
                "success",
                "Company profile updated.",
                CompanyProfileSerializer(company).data,
            )
        return self.build_response(
            "error",
            "Validation failed.",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST,
        )


class CompanyHRProfileView(APIView, ResponseMixin):
    """
    GET: Retrieve the authenticated user's company HR profile.
    PATCH: Update the authenticated user's company HR profile.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not hasattr(request.user, "company_profile"):
            return self.build_response(
                "error", "No company profile found.", {}, status.HTTP_404_NOT_FOUND
            )
        company = request.user.company_profile
        hr_profile, created = CompanyHRProfile.objects.get_or_create(company=company)
        serializer = CompanyHRProfileSerializer(hr_profile)
        return self.build_response(
            "success", "Company HR profile fetched.", serializer.data
        )

    def patch(self, request):
        if not hasattr(request.user, "company_profile"):
            return self.build_response(
                "error", "No company profile found.", {}, status.HTTP_404_NOT_FOUND
            )
        company = request.user.company_profile
        hr_profile, created = CompanyHRProfile.objects.get_or_create(company=company)
        serializer = CompanyHRProfileSerializer(hr_profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return self.build_response(
                "success",
                "Company HR profile updated.",
                serializer.data,
            )
        return self.build_response(
            "error",
            "Validation failed.",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST,
        )


class CompanyCheckView(APIView, ResponseMixin):
    """
    GET: Check if the authenticated user has a company profile.
    Used by the frontend to determine redirect behavior.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        has_company = hasattr(request.user, "company_profile")
        data = {"has_company": has_company}
        if has_company:
            data["company"] = CompanyProfileSerializer(
                request.user.company_profile
            ).data
        return self.build_response("success", "Company check complete.", data)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class StartupListView(generics.ListAPIView):
    permission_classes = (AllowAny,)
    serializer_class = StartupSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        filters = {
            "industry": self.request.query_params.get("industry"),
            "stage": self.request.query_params.get("stage"),
        }
        return StartupService.get_all_startups(filters=filters)


class MyStartupsView(APIView):
    """
    Manage the founder's own startups.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        if request.user.role != "FOUNDER":
            return Response(
                {"detail": "Only founders have startups."},
                status=status.HTTP_403_FORBIDDEN,
            )

        startups = StartupService.get_startups_by_user(request.user)
        serializer = StartupSerializer(startups, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        if request.user.role != "FOUNDER":
            return Response(
                {"detail": "Only founders can create startups."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = StartupCreateUpdateSerializer(data=request.data)
        if serializer.is_valid():
            startup = StartupService.create_startup(
                request.user, serializer.validated_data
            )
            return Response(
                StartupSerializer(startup).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StartupDetailView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, startup_id, *args, **kwargs):
        startup = StartupService.get_startup_by_id(startup_id)
        if not startup:
            return Response(
                {"detail": "Startup not found."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = StartupSerializer(startup)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, startup_id, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        startup = StartupService.get_startup_by_id(startup_id)
        if not startup:
            return Response(
                {"detail": "Startup not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if startup.founder != request.user:
            return Response(
                {"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN
            )

        serializer = StartupCreateUpdateSerializer(data=request.data)
        if serializer.is_valid():
            updated_startup = StartupService.update_startup(
                startup, serializer.validated_data
            )
            return Response(
                StartupSerializer(updated_startup).data, status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, startup_id, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        startup = StartupService.get_startup_by_id(startup_id)
        if not startup:
            return Response(
                {"detail": "Startup not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if startup.founder != request.user:
            return Response(
                {"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN
            )

        StartupService.delete_startup(startup)
        return Response(status=status.HTTP_204_NO_CONTENT)
