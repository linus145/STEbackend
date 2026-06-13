from django.db.models import Count, Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.generics import get_object_or_404, ListAPIView

from jobs.models import JobPost, JobApplication, Skill, TalentPipeline, SavedJob
from jobs.serializers import (
    JobPostListSerializer,
    JobPostDetailSerializer,
    JobPostCreateSerializer,
    JobPostUpdateSerializer,
    JobApplicationSerializer,
    JobApplicationCreateSerializer,
    JobApplicationStatusSerializer,
    SkillSerializer,
    TalentPipelineSerializer,
    SavedJobSerializer,
)
from jobs.permissions import IsCompanyOwner, IsJobOwner
from jobs.services import JobService
from AI.services import AIService
from maincore.pagination import StandardResultsSetPagination


class ResponseMixin:
    """Standardized JSON response helper."""

    def build_response(
        self, status_msg, message, data=None, status_code=status.HTTP_200_OK
    ):
        return Response(
            {
                "status": status_msg,
                "message": message,
                "data": data if data is not None else {},
            },
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
                applications_count=Count(
                    "applications", filter=Q(applications__is_deleted=False)
                )
            ),
            id=job_id,
            status="ACTIVE",
        )
        serializer = JobPostDetailSerializer(job)
        return self.build_response("success", "Job detail fetched.", serializer.data)


class RecruiterJobListView(ListAPIView, ResponseMixin):
    permission_classes = (IsAuthenticated, IsCompanyOwner)
    serializer_class = JobPostListSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        status_filter = self.request.query_params.get("status")
        return JobService.get_recruiter_jobs(
            self.request.user.company_profile, status=status_filter
        )

    def post(self, request):
        if not request.user.company_profile.is_approved:
            return self.build_response(
                "error", "Company pending approval.", {}, status.HTTP_403_FORBIDDEN
            )

        serializer = JobPostCreateSerializer(data=request.data)
        if serializer.is_valid():
            job = serializer.save(company=request.user.company_profile)
            return self.build_response(
                "success",
                "Job created.",
                JobPostDetailSerializer(job).data,
                status.HTTP_201_CREATED,
            )
        return self.build_response(
            "error",
            "Validation failed.",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST,
        )


class ApplyToJobView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, job_id):
        serializer = JobApplicationCreateSerializer(data=request.data)
        if serializer.is_valid():
            try:
                application = JobService.apply_to_job(
                    request.user, job_id, serializer.validated_data
                )
                return self.build_response(
                    "success",
                    "Applied successfully.",
                    JobApplicationSerializer(application).data,
                    status.HTTP_201_CREATED,
                )
            except ValueError as e:
                return self.build_response(
                    "error", str(e), {}, status.HTTP_400_BAD_REQUEST
                )
        return self.build_response(
            "error",
            "Validation failed.",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST,
        )


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
            return self.build_response(
                "success", "Job updated.", JobPostDetailSerializer(job).data
            )
        return self.build_response(
            "error",
            "Validation failed.",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request, job_id):
        job = get_object_or_404(JobPost, id=job_id)
        self.check_object_permissions(request, job)
        job.delete()
        return self.build_response(
            "success", "Job deleted.", {}, status.HTTP_204_NO_CONTENT
        )


class JobApplicationsView(ListAPIView, ResponseMixin):
    permission_classes = (IsAuthenticated, IsJobOwner)
    serializer_class = JobApplicationSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        if not hasattr(self.request.user, "company_profile"):
            return JobApplication.objects.none()
        qs = JobApplication.objects.filter(
            job_id=self.kwargs["job_id"],
            job__company=self.request.user.company_profile,
            is_deleted=False,
            job__is_deleted=False
        ).select_related("applicant")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class UpdateApplicationStatusView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated, IsJobOwner)

    def patch(self, request, application_id):
        application = get_object_or_404(JobApplication, id=application_id)
        self.check_object_permissions(request, application)
        serializer = JobApplicationStatusSerializer(
            application, data=request.data, partial=True
        )
        if serializer.is_valid():
            new_status = serializer.validated_data.get("status")
            serializer.save()

            # If moved to INTERVIEW, auto-orchestrate the AI session
            if new_status == "INTERVIEW":
                try:
                    from AIrounds.services.orchestrator import InterviewOrchestrator

                    InterviewOrchestrator.auto_orchestrate(application)
                except Exception as e:
                    # Log error but don't fail the status update
                    print(f"Auto-orchestration failed: {e}")

            return self.build_response(
                "success", "Status updated.", JobApplicationSerializer(application).data
            )
        return self.build_response(
            "error",
            "Validation failed.",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST,
        )


class MyApplicationsView(ListAPIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)
    serializer_class = JobApplicationSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        qs = JobApplication.objects.filter(
            applicant=self.request.user, is_deleted=False, job__is_deleted=False
        ).select_related("job", "job__company")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class JobApplicationDetailView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated, IsJobOwner)

    def get(self, request, application_id):
        application = get_object_or_404(JobApplication, id=application_id)
        # Ensure the user owns the job for this application
        if application.job.company != request.user.company_profile:
            return self.build_response(
                "error", "Unauthorized", {}, status.HTTP_403_FORBIDDEN
            )

        serializer = JobApplicationSerializer(application)
        return self.build_response(
            "success", "Application detail fetched.", serializer.data
        )


class SkillListView(APIView, ResponseMixin):
    """
    GET: List all available skills, optionally filtered by category.
    POST: Create a new skill (Recruiter only).
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsCompanyOwner()]
        return [AllowAny()]

    def get(self, request):
        category = request.query_params.get("category")
        qs = Skill.objects.all()
        if category:
            qs = qs.filter(category=category)

        serializer = SkillSerializer(qs, many=True)
        return self.build_response("success", "Skills fetched.", serializer.data)

    def post(self, request):
        serializer = SkillSerializer(data=request.data)
        if serializer.is_valid():
            skill = serializer.save()
            return self.build_response(
                "success", "Skill created.", serializer.data, status.HTTP_201_CREATED
            )
        return self.build_response(
            "error",
            "Validation failed.",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST,
        )


class AnalyzeResumesView(APIView, ResponseMixin):
    """
    POST: Triggers AI analysis for all resumes for a specific job.
    """

    permission_classes = (IsAuthenticated, IsJobOwner)

    def post(self, request, job_id):
        job = get_object_or_404(JobPost, id=job_id)
        self.check_object_permissions(request, job)

        # Import AI models here to avoid circular imports
        from AI.models import AIScreeningReport

        # 1. Validate AI Configuration


# ─── Talent Pipeline Views ──────────────────────────────────────────


class SaveToPipelineView(APIView, ResponseMixin):
    """
    POST: Save a talent (user) to the recruiter's company pipeline.
    """

    permission_classes = (IsAuthenticated, IsCompanyOwner)

    def post(self, request):
        talent_id = request.data.get("talent_id")
        if not talent_id:
            return self.build_response(
                "error", "Talent ID is required.", {}, status.HTTP_400_BAD_REQUEST
            )

        from django.contrib.auth import get_user_model

        User = get_user_model()
        talent = get_object_or_404(User, id=talent_id)

        pipeline_entry = TalentPipeline.all_objects.filter(
            company=request.user.company_profile, talent=talent
        ).first()

        if pipeline_entry:
            if pipeline_entry.is_deleted:
                pipeline_entry.restore()
                pipeline_entry.status = "LEAD"
                if request.data.get("notes"):
                    pipeline_entry.notes = request.data.get("notes")
                pipeline_entry.save()
            else:
                return self.build_response(
                    "error",
                    "Talent is already in your pipeline.",
                    {},
                    status.HTTP_400_BAD_REQUEST,
                )
        else:
            pipeline_entry = TalentPipeline.objects.create(
                company=request.user.company_profile,
                talent=talent,
                notes=request.data.get("notes", ""),
            )

        return self.build_response(
            "success",
            "Talent saved to pipeline.",
            TalentPipelineSerializer(pipeline_entry).data,
            status.HTTP_201_CREATED,
        )


class TalentPipelineListView(ListAPIView, ResponseMixin):
    """
    GET: List all talents in the recruiter's company pipeline.
    """

    permission_classes = (IsAuthenticated, IsCompanyOwner)
    serializer_class = TalentPipelineSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return TalentPipeline.objects.filter(
            company=self.request.user.company_profile, is_deleted=False
        ).select_related("talent")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return self.build_response(
            "success", "Pipeline talents fetched.", serializer.data
        )


class TalentPipelineDetailView(APIView, ResponseMixin):
    """
    PATCH: Update a talent pipeline entry (status/notes).
    DELETE: Remove a talent from the pipeline.
    """

    permission_classes = (IsAuthenticated, IsCompanyOwner)

    def patch(self, request, entry_id):
        entry = get_object_or_404(
            TalentPipeline, id=entry_id, company=request.user.company_profile
        )
        serializer = TalentPipelineSerializer(entry, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return self.build_response("success", "Pipeline updated.", serializer.data)
        return self.build_response(
            "error",
            "Validation failed.",
            serializer.errors,
            status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request, entry_id):
        entry = get_object_or_404(
            TalentPipeline, id=entry_id, company=request.user.company_profile
        )
        entry.delete()
        return self.build_response(
            "success", "Removed from pipeline.", {}, status.HTTP_204_NO_CONTENT
        )


class SavedJobListView(ListAPIView, ResponseMixin):
    """
    GET: List all jobs saved by the authenticated user.
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = SavedJobSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return SavedJob.objects.filter(
            user=self.request.user,
            job__is_deleted=False
        ).select_related("job", "job__company")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return self.build_response(
            "success", "Saved jobs fetched.", serializer.data
        )


class SavedJobIdsView(APIView, ResponseMixin):
    """
    GET: Get all saved job IDs for the authenticated user.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        ids = list(SavedJob.objects.filter(
            user=request.user,
            job__is_deleted=False
        ).values_list("job_id", flat=True))
        # Convert UUID objects to strings
        str_ids = [str(id) for id in ids]
        return self.build_response(
            "success",
            "Saved job IDs fetched.",
            {"saved_job_ids": str_ids}
        )


class ToggleSaveJobView(APIView, ResponseMixin):
    """
    POST: Toggle saving/unsaving of a job post by the authenticated user.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request, job_id):
        job = get_object_or_404(JobPost, id=job_id, is_deleted=False)
        saved_job, created = SavedJob.objects.get_or_create(
            user=request.user,
            job=job
        )

        if not created:
            # If it already existed, we unsave it
            saved_job.delete()
            return self.build_response(
                "success",
                "Job unsaved successfully.",
                {"saved": False, "job_id": str(job_id)}
            )
        
        return self.build_response(
            "success",
            "Job saved successfully.",
            {"saved": True, "job_id": str(job_id)},
            status_code=status.HTTP_201_CREATED
        )
