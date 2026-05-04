from django.db.models import Count, Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.generics import get_object_or_404, ListAPIView

from .models import JobPost, JobApplication, Skill
from .serializers import (
    JobPostListSerializer,
    JobPostDetailSerializer,
    JobPostCreateSerializer,
    JobPostUpdateSerializer,
    JobApplicationSerializer,
    JobApplicationCreateSerializer,
    JobApplicationStatusSerializer,
    SkillSerializer,
)
from .permissions import IsCompanyOwner, IsJobOwner
from .services import JobService
from AI.services import AIService
from maincore.pagination import StandardResultsSetPagination


class ResponseMixin:
    """Standardized JSON response helper."""

    def build_response(
        self, status_msg, message, data=None, status_code=status.HTTP_200_OK
    ):
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
        qs = JobApplication.objects.filter(
            job_id=self.kwargs["job_id"], is_deleted=False
        ).select_related("applicant")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class UpdateApplicationStatusView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated, IsCompanyOwner)

    def patch(self, request, application_id):
        application = get_object_or_404(JobApplication, id=application_id)
        self.check_object_permissions(request, application)
        serializer = JobApplicationStatusSerializer(
            application, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
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
            applicant=self.request.user, is_deleted=False
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
    """

    permission_classes = (AllowAny,)  # Allow public fetching for dropdowns

    def get(self, request):
        category = request.query_params.get("category")
        qs = Skill.objects.all()
        if category:
            qs = qs.filter(category=category)

        serializer = SkillSerializer(qs, many=True)
        return self.build_response("success", "Skills fetched.", serializer.data)


class AnalyzeResumesView(APIView, ResponseMixin):
    """
    POST: Triggers AI analysis for all resumes for a specific job.
    """

    permission_classes = (IsAuthenticated, IsJobOwner)

    def post(self, request, job_id):
        job = get_object_or_404(JobPost, id=job_id)
        self.check_object_permissions(request, job)

        # 1. Validate AI Configuration
        from django.conf import settings as django_settings

        if not getattr(django_settings, "GEMINI_API_KEY", None):
            return self.build_response(
                "error",
                "AI service not configured. Please set GEMINI_API_KEY.",
                {},
                status.HTTP_400_BAD_REQUEST,
            )

        # 2. Get Applications for this Job
        all_apps_count = job.applications.filter(is_deleted=False).count()
        if all_apps_count == 0:
            return self.build_response(
                "error",
                "No applications found for this job.",
                {},
                status.HTTP_400_BAD_REQUEST,
            )

        applications = list(job.applications.filter(status="PENDING", is_deleted=False))
        processed_count = 0
        errors = []

        if applications:
            # 3. Separate apps with/without resumes
            apps_with_resume = []
            skipped_no_resume = 0
            for app in applications:
                if app.resume_url:
                    apps_with_resume.append(app)
                else:
                    skipped_no_resume += 1

            # 4. Parallel AI screening — process up to 5 resumes at once
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import threading

            skipped_extract_fail = 0
            lock = threading.Lock()

            def screen_one(app):
                """Screen a single resume in its own thread."""
                try:
                    # Include explicit skills in the analysis for better matching
                    job_skills = ", ".join([s.name for s in job.skills.all()])
                    full_job_info = f"{job.description}\n\nREQUIRED SKILLS: {job_skills}"
                    score, analysis = AIService.analyze_resume(
                        job.title, full_job_info, app.resume_url
                    )
                    return app, score, analysis
                except Exception as e:
                    return app, None, str(e)

            if apps_with_resume:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {
                        executor.submit(screen_one, app): app for app in apps_with_resume
                    }

                    for future in as_completed(futures):
                        app, score, analysis = future.result()

                        if score is None:
                            with lock:
                                skipped_extract_fail += 1
                                errors.append(f"{app.applicant.email}: {analysis}")
                            continue

                        # Update Application
                        app.ai_score = score
                        app.ai_analysis = analysis
                        if app.status == "PENDING":
                            app.status = "REVIEWED"
                        app.save()
                        with lock:
                            processed_count += 1
            else:
                # All applications had no resumes
                pass

        # 5. Top Candidates — ATS-style ranking
        # Show top N where N = max(open_positions, 10), or all if fewer than 10
        all_scored = (
            job.applications.filter(ai_score__isnull=False, is_deleted=False)
            .select_related("applicant")
            .order_by("-ai_score")
        )
        total_scored = all_scored.count()
        openings = job.open_positions or 1

        # If less than 10 applicants, show all. Otherwise show at least top 10 or openings count.
        if total_scored <= 10:
            limit = total_scored
        else:
            limit = max(openings, 10)

        top_candidates_qs = all_scored[:limit]

        results_data = []
        for rank, cand in enumerate(top_candidates_qs, 1):
            results_data.append(
                {
                    "id": str(cand.id),
                    "rank": rank,
                    "name": f"{cand.applicant.first_name} {cand.applicant.last_name}",
                    "email": cand.applicant.email,
                    "score": cand.ai_score,
                    "summary": (cand.ai_analysis[:1500] + "...")
                    if cand.ai_analysis and len(cand.ai_analysis) > 1500
                    else (cand.ai_analysis or ""),
                    "recommended": rank <= openings,  # Top N for the openings
                }
            )

        # Build response
        if processed_count > 0:
            msg = f"Successfully screened {processed_count} resume(s)."
            if errors:
                msg += f" {len(errors)} resume(s) failed."
        else:
            msg = "All candidates screened successfully. No pending resumes left to analyze."

        return self.build_response(
            "success",
            msg,
            {
                "processed_count": processed_count,
                "total_applicants": total_scored,
                "top_candidates": results_data,
                "openings": openings,
                "errors": errors if errors else [],
            },
        )
