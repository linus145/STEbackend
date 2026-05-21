from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import permissions
from rest_framework.views import APIView
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
from maincore.pagination import StandardResultsSetPagination


class ResponseMixin:
    """Standardized JSON response helper."""
    def build_response(self, status_msg, message, data=None, status_code=status.HTTP_200_OK):
        return Response(
            {"status": status_msg, "message": message, "data": data if data is not None else {}},
            status=status_code,
        )

# ─── Company Profile Views ─────────────────────────────────────────

class CompanyRegisterView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        if hasattr(request.user, "company_profile"):
            return self.build_response("error", "Already registered.", CompanyProfileSerializer(request.user.company_profile).data, status.HTTP_400_BAD_REQUEST)

        serializer = CompanyRegisterSerializer(data=request.data)
        if serializer.is_valid():
            company = StartupService.create_company_profile(request.user, serializer.validated_data)
            return self.build_response("success", "Company registered.", CompanyProfileSerializer(company).data, status.HTTP_201_CREATED)
        return self.build_response("error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)


class CompanyLoginView(APIView, ResponseMixin):
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = CompanyLoginSerializer(data=request.data)
        if serializer.is_valid():
            user, company = StartupService.authenticate_company(
                serializer.validated_data["email"], 
                serializer.validated_data["password"]
            )
            if user:
                tokens = UserService.generate_tokens(user)
                from useraccounts.views import _set_auth_cookies
                response = self.build_response("success", "Login successful.", {
                    "user": UserSerializer(user).data,
                    "company": CompanyProfileSerializer(company).data,
                })
                return _set_auth_cookies(response, tokens["access"], tokens["refresh"])
            return self.build_response("error", "Invalid credentials.", {}, status.HTTP_401_UNAUTHORIZED)
        return self.build_response("error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)


class StartupListView(generics.ListAPIView):
    """
    GET: List all startups with pagination and optimized queries.
    """
    permission_classes = (AllowAny,)
    serializer_class = StartupSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        filters = {
            "industry": self.request.query_params.get("industry"),
            "stage": self.request.query_params.get("stage"),
        }
        return StartupService.get_all_startups(filters)


class MyStartupsView(generics.ListAPIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)
    serializer_class = StartupSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return StartupService.get_startups_by_user(self.request.user)

    def post(self, request):
        if request.user.role != "FOUNDER":
            return self.build_response("error", "Only founders can create startups.", {}, status.HTTP_403_FORBIDDEN)

        serializer = StartupCreateUpdateSerializer(data=request.data)
        if serializer.is_valid():
            startup = StartupService.create_startup(request.user, serializer.validated_data)
            return self.build_response("success", "Startup created.", StartupSerializer(startup).data, status.HTTP_201_CREATED)
        return self.build_response("error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)
class CompanyProfileView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not hasattr(request.user, "company_profile"):
            return self.build_response("error", "No company profile found.", {}, status.HTTP_404_NOT_FOUND)
        serializer = CompanyProfileSerializer(request.user.company_profile)
        return self.build_response("success", "Company profile fetched.", serializer.data)

    def patch(self, request):
        if not hasattr(request.user, "company_profile"):
            return self.build_response("error", "No company profile found.", {}, status.HTTP_404_NOT_FOUND)
        serializer = CompanyUpdateSerializer(request.user.company_profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return self.build_response("success", "Company profile updated.", CompanyProfileSerializer(request.user.company_profile).data)
        return self.build_response("error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)


class CompanyHRProfileView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not hasattr(request.user, "company_profile"):
            return self.build_response("error", "No company profile found.", {}, status.HTTP_404_NOT_FOUND)
        hr_profile = CompanyHRProfile.objects.filter(company=request.user.company_profile, is_deleted=False).first()
        if not hr_profile:
            hr_profile = CompanyHRProfile.objects.create(company=request.user.company_profile)
        serializer = CompanyHRProfileSerializer(hr_profile)
        return self.build_response("success", "HR profile fetched.", serializer.data)

    def patch(self, request):
        if not hasattr(request.user, "company_profile"):
            return self.build_response("error", "No company profile found.", {}, status.HTTP_404_NOT_FOUND)
        hr_profile = CompanyHRProfile.objects.filter(company=request.user.company_profile, is_deleted=False).first()
        if not hr_profile:
            hr_profile = CompanyHRProfile.objects.create(company=request.user.company_profile)
        serializer = CompanyHRProfileSerializer(hr_profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return self.build_response("success", "HR profile updated.", serializer.data)
        return self.build_response("error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)


class CompanyHRProfileListCreateView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not hasattr(request.user, "company_profile"):
            return self.build_response("error", "No company profile found.", {}, status.HTTP_404_NOT_FOUND)
        profiles = CompanyHRProfile.objects.filter(company=request.user.company_profile, is_deleted=False).order_by("-created_at")
        serializer = CompanyHRProfileSerializer(profiles, many=True)
        return self.build_response("success", "HR profiles fetched.", serializer.data)

    def post(self, request):
        if not hasattr(request.user, "company_profile"):
            return self.build_response("error", "No company profile found.", {}, status.HTTP_404_NOT_FOUND)
        serializer = CompanyHRProfileSerializer(data=request.data)
        if serializer.is_valid():
            profile = serializer.save(company=request.user.company_profile)
            return self.build_response("success", "HR profile created.", CompanyHRProfileSerializer(profile).data, status.HTTP_201_CREATED)
        return self.build_response("error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)


class CompanyHRProfileDetailView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def get_object(self, request, pk):
        if not hasattr(request.user, "company_profile"):
            return None
        try:
            return CompanyHRProfile.objects.get(
                pk=pk,
                company=request.user.company_profile,
                is_deleted=False
            )
        except CompanyHRProfile.DoesNotExist:
            return None

    def get(self, request, pk):
        profile = self.get_object(request, pk)
        if not profile:
            return self.build_response("error", "HR profile not found.", {}, status.HTTP_404_NOT_FOUND)
        serializer = CompanyHRProfileSerializer(profile)
        return self.build_response("success", "HR profile fetched.", serializer.data)

    def patch(self, request, pk):
        profile = self.get_object(request, pk)
        if not profile:
            return self.build_response("error", "HR profile not found.", {}, status.HTTP_404_NOT_FOUND)
        serializer = CompanyHRProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return self.build_response("success", "HR profile updated.", serializer.data)
        return self.build_response("error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        profile = self.get_object(request, pk)
        if not profile:
            return self.build_response("error", "HR profile not found.", {}, status.HTTP_404_NOT_FOUND)
        profile.delete()
        return self.build_response("success", "HR profile deleted.", {}, status.HTTP_200_OK)


class CompanyCheckView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        has_company = hasattr(request.user, "company_profile")
        data = {"has_company": has_company}
        if has_company:
            data["company"] = CompanyProfileSerializer(request.user.company_profile).data
        return self.build_response("success", "Check complete.", data)


class StartupDetailView(APIView, ResponseMixin):
    permission_classes = (AllowAny,)

    def get(self, request, startup_id):
        startup = StartupService.get_startup_by_id(startup_id)
        if not startup:
            return self.build_response("error", "Startup not found.", {}, status.HTTP_404_NOT_FOUND)
        serializer = StartupSerializer(startup)
        return self.build_response("success", "Startup detail fetched.", serializer.data)

    def put(self, request, startup_id):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        startup = StartupService.get_startup_by_id(startup_id)
        if not startup or startup.founder != request.user:
            return self.build_response("error", "Not authorized.", {}, status.HTTP_403_FORBIDDEN)
        
        serializer = StartupCreateUpdateSerializer(startup, data=request.data)
        if serializer.is_valid():
            startup = StartupService.update_startup(startup, serializer.validated_data)
            return self.build_response("success", "Startup updated.", StartupSerializer(startup).data)
        return self.build_response("error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)

    def delete(self, request, startup_id):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        startup = StartupService.get_startup_by_id(startup_id)
        if not startup or startup.founder != request.user:
            return self.build_response("error", "Not authorized.", {}, status.HTTP_403_FORBIDDEN)
        StartupService.delete_startup(startup)
        return self.build_response("success", "Startup deleted.", {}, status.HTTP_204_NO_CONTENT)
