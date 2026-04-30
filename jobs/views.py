from django.db.models import Count, Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.generics import get_object_or_404, ListAPIView

from .models import JobPost, JobApplication
from .serializers import (
    JobPostListSerializer,
    JobPostDetailSerializer,
    JobPostCreateSerializer,
    JobPostUpdateSerializer,
    JobApplicationSerializer,
    JobApplicationCreateSerializer,
    JobApplicationStatusSerializer,
)
from .permissions import IsCompanyOwner, IsJobOwner
from .services import JobService
from maincore.pagination import StandardResultsSetPagination


class ResponseMixin:
    """Standardized JSON response helper."""
    def build_response(self, status_msg, message, data=None, status_code=status.HTTP_200_OK):
        return Response(
            {"status": status_msg, "message": message, "data": data or {}},
            status=status_code,
        )

# ─── Job Post Views ────────────────────────────────────────────────

class PublicJobListView(ListAPIView, ResponseMixin):
    """
    GET: List all active job posts (public) with pagination and optimized queries.
    """
    permission_classes = (AllowAny,)
    serializer_class = JobPostListSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        filters = {
            "job_type": self.request.query_params.get("job_type"),
            "work_mode": self.request.query_params.get("work_mode"),
            "experience_level": self.request.query_params.get("experience_level"),
            "search": self.request.query_params.get("search"),
        }
        return JobService.get_active_jobs(filters)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return self.build_response("success", "Jobs fetched.", serializer.data)


class JobPostDetailView(APIView, ResponseMixin):
    permission_classes = (AllowAny,)

    def get(self, request, job_id):
        job = get_object_or_404(
            JobPost.objects.select_related("company").annotate(
                applications_count=Count("applications", filter=Q(applications__is_deleted=False))
            ), 
            id=job_id, 
            status="ACTIVE"
        )
        serializer = JobPostDetailSerializer(job)
        return self.build_response("success", "Job detail fetched.", serializer.data)


class RecruiterJobListView(ListAPIView, ResponseMixin):
    permission_classes = (IsAuthenticated, IsCompanyOwner)
    serializer_class = JobPostListSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        status_filter = self.request.query_params.get("status")
        return JobService.get_recruiter_jobs(self.request.user.company_profile, status=status_filter)

    def post(self, request):
        if not request.user.company_profile.is_approved:
            return self.build_response(
                "error", "Company pending approval.", {}, status.HTTP_403_FORBIDDEN
            )

        serializer = JobPostCreateSerializer(data=request.data)
        if serializer.is_valid():
            job = serializer.save(company=request.user.company_profile)
            return self.build_response("success", "Job created.", JobPostDetailSerializer(job).data, status.HTTP_201_CREATED)
        return self.build_response("error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)


class ApplyToJobView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, job_id):
        serializer = JobApplicationCreateSerializer(data=request.data)
        if serializer.is_valid():
            try:
                application = JobService.apply_to_job(request.user, job_id, serializer.validated_data)
                return self.build_response("success", "Applied successfully.", JobApplicationSerializer(application).data, status.HTTP_201_CREATED)
            except ValueError as e:
                return self.build_response("error", str(e), {}, status.HTTP_400_BAD_REQUEST)
        return self.build_response("error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)


class RecruiterDashboardStatsView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated, IsCompanyOwner)

    def get(self, request):
        stats = JobService.get_dashboard_stats(request.user.company_profile)
        return self.build_response("success", "Stats fetched.", stats)


class RecruiterJobDetailView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated, IsJobOwner)

    def get(self, request, job_id):
        job = get_object_or_404(JobPost, id=job_id)
        self.check_object_permissions(request, job)
        serializer = JobPostDetailSerializer(job)
        return self.build_response("success", "Job detail fetched.", serializer.data)

    def patch(self, request, job_id):
        job = get_object_or_404(JobPost, id=job_id)
        self.check_object_permissions(request, job)
        serializer = JobPostUpdateSerializer(job, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return self.build_response("success", "Job updated.", JobPostDetailSerializer(job).data)
        return self.build_response("error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)

    def delete(self, request, job_id):
        job = get_object_or_404(JobPost, id=job_id)
        self.check_object_permissions(request, job)
        job.delete()
        return self.build_response("success", "Job deleted.", {}, status.HTTP_204_NO_CONTENT)


class JobApplicationsView(ListAPIView, ResponseMixin):
    permission_classes = (IsAuthenticated, IsJobOwner)
    serializer_class = JobApplicationSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = JobApplication.objects.filter(job_id=self.kwargs["job_id"], is_deleted=False).select_related("applicant")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class UpdateApplicationStatusView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated, IsCompanyOwner)

    def patch(self, request, application_id):
        application = get_object_or_404(JobApplication, id=application_id)
        self.check_object_permissions(request, application)
        serializer = JobApplicationStatusSerializer(application, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return self.build_response("success", "Status updated.", JobApplicationSerializer(application).data)
        return self.build_response("error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST)


class MyApplicationsView(ListAPIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)
    serializer_class = JobApplicationSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = JobApplication.objects.filter(applicant=self.request.user, is_deleted=False).select_related("job", "job__company")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

