from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.generics import get_object_or_404
from django.db.models import Count, Q

from startups.models import CompanyProfile
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


class ResponseMixin:
    """Standardized JSON response helper — mirrors useraccounts pattern."""

    def build_response(self, status_msg, message, data=None, status_code=status.HTTP_200_OK):
        return Response(
            {"status": status_msg, "message": message, "data": data or {}},
            status=status_code,
        )



# ─── Job Post Views ────────────────────────────────────────────────


class PublicJobListView(APIView, ResponseMixin):
    """
    GET: List all active job posts (public — for job browsing).
    """

    permission_classes = (AllowAny,)

    def get(self, request):
        jobs = (
            JobPost.objects.filter(status="ACTIVE")
            .select_related("company")
            .annotate(applications_count=Count("applications", filter=Q(applications__is_deleted=False)))
            .order_by("-created_at")
        )

        # Optional filters
        job_type = request.query_params.get("job_type")
        work_mode = request.query_params.get("work_mode")
        experience = request.query_params.get("experience_level")
        search = request.query_params.get("search")

        if job_type:
            jobs = jobs.filter(job_type=job_type)
        if work_mode:
            jobs = jobs.filter(work_mode=work_mode)
        if experience:
            jobs = jobs.filter(experience_level=experience)
        if search:
            jobs = jobs.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(company__company_name__icontains=search)
            )

        serializer = JobPostListSerializer(jobs, many=True)
        return self.build_response("success", "Jobs fetched.", serializer.data)


class JobPostDetailView(APIView, ResponseMixin):
    """
    GET: View a single job post detail (public).
    """

    permission_classes = (AllowAny,)

    def get(self, request, job_id):
        job = get_object_or_404(JobPost, id=job_id, status="ACTIVE")
        job.applications_count = job.applications.filter(is_deleted=False).count()
        serializer = JobPostDetailSerializer(job)
        return self.build_response("success", "Job detail fetched.", serializer.data)


class RecruiterJobListView(APIView, ResponseMixin):
    """
    GET: List the recruiter's own job posts (all statuses).
    POST: Create a new job post.
    """

    permission_classes = (IsAuthenticated, IsCompanyOwner)

    def get(self, request):
        company = request.user.company_profile
        jobs = (
            company.job_posts.filter(is_deleted=False)
            .annotate(applications_count=Count("applications", filter=Q(applications__is_deleted=False)))
            .order_by("-created_at")
        )

        # Optional status filter
        status_filter = request.query_params.get("status")
        if status_filter:
            jobs = jobs.filter(status=status_filter)

        serializer = JobPostListSerializer(jobs, many=True)
        return self.build_response("success", "Your jobs fetched.", serializer.data)

    def post(self, request):
        if not request.user.company_profile.is_approved:
            return self.build_response(
                "error", "Your company profile is pending approval. You cannot post jobs yet.", {}, status.HTTP_403_FORBIDDEN
            )

        serializer = JobPostCreateSerializer(data=request.data)
        if serializer.is_valid():
            job = serializer.save(company=request.user.company_profile)
            return self.build_response(
                "success",
                "Job post created.",
                JobPostDetailSerializer(job).data,
                status.HTTP_201_CREATED,
            )
        return self.build_response(
            "error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST
        )


class RecruiterJobDetailView(APIView, ResponseMixin):
    """
    GET: View own job post detail.
    PATCH: Update own job post.
    DELETE: Soft-delete own job post.
    """

    permission_classes = (IsAuthenticated, IsCompanyOwner, IsJobOwner)

    def _get_job(self, request, job_id):
        job = get_object_or_404(JobPost, id=job_id, is_deleted=False)
        self.check_object_permissions(request, job)
        return job

    def get(self, request, job_id):
        job = self._get_job(request, job_id)
        job.applications_count = job.applications.filter(is_deleted=False).count()
        serializer = JobPostDetailSerializer(job)
        return self.build_response("success", "Job detail fetched.", serializer.data)

    def patch(self, request, job_id):
        if not request.user.company_profile.is_approved:
            return self.build_response(
                "error", "Your company profile is pending approval. You cannot modify jobs.", {}, status.HTTP_403_FORBIDDEN
            )
        job = self._get_job(request, job_id)
        serializer = JobPostUpdateSerializer(job, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return self.build_response(
                "success",
                "Job post updated.",
                JobPostDetailSerializer(job).data,
            )
        return self.build_response(
            "error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, job_id):
        job = self._get_job(request, job_id)
        job.delete()  # Soft delete from SoftDeleteModel
        return self.build_response("success", "Job post deleted.", {}, status.HTTP_200_OK)


# ─── Job Application Views ─────────────────────────────────────────


class ApplyToJobView(APIView, ResponseMixin):
    """
    POST: Apply to a job post.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request, job_id):
        job = get_object_or_404(JobPost, id=job_id, status="ACTIVE")

        # Prevent applying to own company's jobs
        if hasattr(request.user, "company_profile") and job.company == request.user.company_profile:
            return self.build_response(
                "error",
                "You cannot apply to your own company's job.",
                {},
                status.HTTP_400_BAD_REQUEST,
            )

        # Check for existing application (including soft-deleted ones)
        existing_app = JobApplication.all_objects.filter(job=job, applicant=request.user).first()
        if existing_app:
            if not existing_app.is_deleted:
                return self.build_response(
                    "error",
                    "You have already applied to this job.",
                    {},
                    status.HTTP_400_BAD_REQUEST,
                )
            else:
                # Restore the deleted application and update it with new data
                existing_app.restore()
                serializer = JobApplicationCreateSerializer(existing_app, data=request.data)
                if serializer.is_valid():
                    serializer.save()
                    return self.build_response(
                        "success",
                        "Application restored and submitted.",
                        JobApplicationSerializer(existing_app).data,
                    )
                return self.build_response(
                    "error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST
                )

        serializer = JobApplicationCreateSerializer(data=request.data)
        if serializer.is_valid():
            application = serializer.save(job=job, applicant=request.user)
            return self.build_response(
                "success",
                "Application submitted.",
                JobApplicationSerializer(application).data,
                status.HTTP_201_CREATED,
            )
        
        # Log errors for debugging (visible in server terminal)
        print(f"Job application validation failed for job {job_id}: {serializer.errors}")
        
        return self.build_response(
            "error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST
        )


class JobApplicationsView(APIView, ResponseMixin):
    """
    GET: View all applications for a specific job (recruiter only).
    """

    permission_classes = (IsAuthenticated, IsCompanyOwner)

    def get(self, request, job_id):
        job = get_object_or_404(JobPost, id=job_id, is_deleted=False)

        # Verify ownership
        if job.company.owner != request.user:
            return self.build_response(
                "error", "You do not own this job post.", {}, status.HTTP_403_FORBIDDEN
            )

        # Optional status filter
        applications = job.applications.filter(is_deleted=False).select_related("applicant")
        status_filter = request.query_params.get("status")
        if status_filter:
            applications = applications.filter(status=status_filter)

        serializer = JobApplicationSerializer(applications, many=True)
        return self.build_response("success", "Applications fetched.", serializer.data)


class UpdateApplicationStatusView(APIView, ResponseMixin):
    """
    PATCH: Update the status of a job application (recruiter only).
    """

    permission_classes = (IsAuthenticated, IsCompanyOwner)

    def patch(self, request, application_id):
        if not request.user.company_profile.is_approved:
            return self.build_response(
                "error", "Your company profile is pending approval. You cannot update applications.", {}, status.HTTP_403_FORBIDDEN
            )
        application = get_object_or_404(JobApplication, id=application_id, is_deleted=False)

        # Verify ownership through the job → company chain
        if application.job.company.owner != request.user:
            return self.build_response(
                "error", "You do not own this application's job.", {}, status.HTTP_403_FORBIDDEN
            )

        serializer = JobApplicationStatusSerializer(data=request.data)
        if serializer.is_valid():
            application.status = serializer.validated_data["status"]
            application.save()
            return self.build_response(
                "success",
                f"Application status updated to {application.status}.",
                JobApplicationSerializer(application).data,
            )
        return self.build_response(
            "error", "Validation failed.", serializer.errors, status.HTTP_400_BAD_REQUEST
        )


class MyApplicationsView(APIView, ResponseMixin):
    """
    GET: View the authenticated user's own job applications.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        applications = (
            JobApplication.objects.filter(applicant=request.user, is_deleted=False)
            .select_related("job", "job__company")
            .order_by("-applied_at")
        )
        serializer = JobApplicationSerializer(applications, many=True)
        return self.build_response("success", "Your applications fetched.", serializer.data)


# ─── Dashboard Stats ───────────────────────────────────────────────


class RecruiterDashboardStatsView(APIView, ResponseMixin):
    """
    GET: Aggregate recruitment statistics for the dashboard.
    """

    permission_classes = (IsAuthenticated, IsCompanyOwner)

    def get(self, request):
        company = request.user.company_profile
        jobs = company.job_posts.filter(is_deleted=False)
        applications = JobApplication.objects.filter(
            job__company=company, is_deleted=False
        )

        data = {
            "total_jobs": jobs.count(),
            "active_jobs": jobs.filter(status="ACTIVE").count(),
            "draft_jobs": jobs.filter(status="DRAFT").count(),
            "closed_jobs": jobs.filter(status="CLOSED").count(),
            "total_applications": applications.count(),
            "pending_applications": applications.filter(status="PENDING").count(),
            "reviewed": applications.filter(status="REVIEWED").count(),
            "shortlisted": applications.filter(status="SHORTLISTED").count(),
            "rejected": applications.filter(status="REJECTED").count(),
            "hired": applications.filter(status="HIRED").count(),
        }
        return self.build_response("success", "Dashboard stats fetched.", data)
