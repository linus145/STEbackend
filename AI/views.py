import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from jobs.models import JobApplication, JobPost

from AI.models import AIScreeningReport
from AI.serializers import AIScreeningReportSerializer
from AI.services import AIService

User = get_user_model()


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


class AIScreeningHistoryView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        # Only show reports for jobs that are currently ACTIVE
        active_job_ids = JobPost.objects.filter(
            company=request.user.company_profile, status="ACTIVE", is_deleted=False
        ).values_list("id", flat=True)
        reports = AIScreeningReport.objects.filter(
            recruiter=request.user, is_deleted=False, job_id__in=active_job_ids
        ).order_by("-created_at")
        serializer = AIScreeningReportSerializer(reports, many=True)
        return Response(
            {
                "status": "success",
                "message": "Screening history fetched.",
                "data": serializer.data,
            }
        )


class AnalyzeResumesView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, job_id):
        try:
            job = JobPost.objects.get(id=job_id)
        except JobPost.DoesNotExist:
            return self.build_response(
                "error", "Job post not found.", {}, status.HTTP_404_NOT_FOUND
            )

        # 1. Get Applications
        applications = list(job.applications.filter(status="PENDING", is_deleted=False))
        app_ids = [app.id for app in applications]
        if not applications:
            all_scored_qs = job.applications.filter(
                ai_score__isnull=False, is_deleted=False
            ).order_by("-ai_score")
            total_scored = all_scored_qs.count()

            if total_scored > 0:
                results_data = []
                for rank, cand in enumerate(all_scored_qs[:25], 1):
                    summary = ""
                    analysis_obj = None
                    try:
                        if cand.ai_analysis and cand.ai_analysis.strip().startswith(
                            "{"
                        ):
                            analysis_obj = json.loads(cand.ai_analysis)
                            summary = analysis_obj.get("recruiter_view", {}).get(
                                "explanation", ""
                            )
                    except:
                        pass
                    if not summary:
                        summary = (
                            (cand.ai_analysis[:500] + "...")
                            if cand.ai_analysis and len(cand.ai_analysis) > 500
                            else (cand.ai_analysis or "No analysis available.")
                        )

                    results_data.append(
                        {
                            "id": str(cand.id),
                            "rank": rank,
                            "name": f"{cand.applicant.first_name} {cand.applicant.last_name}",
                            "email": cand.applicant.email,
                            "score": cand.ai_score,
                            "summary": summary,
                            "analysis": analysis_obj,
                        }
                    )

                return self.build_response(
                    "success",
                    "All candidates screened successfully.",
                    {
                        "processed_count": 0,
                        "total_applicants": total_scored,
                        "top_candidates": results_data,
                    },
                )
            return self.build_response(
                "error",
                "No pending applications found.",
                {},
                status.HTTP_400_BAD_REQUEST,
            )

        # 2. Prevent Multiple Concurrent Screenings (with stale check)
        from django.utils import timezone
        from datetime import timedelta

        two_minutes_ago = timezone.now() - timedelta(minutes=2)
        existing_report = AIScreeningReport.objects.filter(
            job_id=job.id, results__status="processing"
        ).first()

        # If a report is processing but older than 2 min, it's likely stuck — allow restart
        is_stale = existing_report and existing_report.created_at < two_minutes_ago

        if existing_report and not is_stale:
            return self.build_response(
                "success",
                "Screening in progress.",
                {
                    **existing_report.results,
                    "report_id": str(existing_report.id),
                    "job_id": str(job.id),
                },
                status_code=status.HTTP_202_ACCEPTED,
            )

        # Mark any stale reports as failed so they don't block future runs
        if existing_report and is_stale:
            existing_report.results["status"] = "failed"
            existing_report.results["error"] = "Timed out — marked as stale"
            existing_report.save()

        # 3. Create Processing Report
        report = AIScreeningReport.objects.create(
            job_id=job.id,
            job_title=job.title,
            recruiter=request.user,
            results={
                "status": "processing",
                "job_id": str(job.id),
                "count": len(applications),
                "total_applicants": len(applications),
                "top_candidates": [],
            },
        )

        # FAST STATUS UPDATE: Update all targeted apps to REVIEWED immediately
        # so the agent can see the state change without waiting for the AI thread.
        # This prevents sync delays for the autonomous agent.
        JobApplication.objects.filter(id__in=app_ids, status="PENDING").update(
            status="REVIEWED"
        )

        # 4. Background Thread Logic
        def run_screening_background(job_id, user_id, app_ids, report_id):
            # Close inherited connection to force a fresh one in this thread
            connection.close()

            report = None
            try:
                # Ensure fresh DB connection
                connection.ensure_connection()

                # Re-fetch objects in this thread's context
                job = JobPost.objects.get(id=job_id)
                user = User.objects.get(id=user_id)
                report = AIScreeningReport.objects.get(id=report_id)
                apps_to_screen = list(
                    JobApplication.objects.filter(id__in=app_ids).select_related(
                        "applicant"
                    )
                )

                print(
                    f"[AI] Background thread started. Screening {len(apps_to_screen)} candidates for job: {job.title}"
                )

                processed_count = 0
                errors = []
                job_skills = ", ".join([s.name for s in job.skills.all()])
                full_job_info = f"{job.description}\n\nREQUIRED SKILLS: {job_skills}"

                def screen_one(app):
                    # Each thread worker needs its own connection
                    connection.close()
                    try:
                        print(
                            f"[AI] Starting screening for candidate: {app.applicant.email}"
                        )
                        score, analysis_json = AIService.analyze_resume(
                            job.title, full_job_info, app.resume_url
                        )
                        print(
                            f"[AI] Finished screening {app.applicant.email}: score={score}"
                        )
                        return app.id, score, analysis_json
                    except Exception as e:
                        print(f"[AI] Error screening {app.applicant.email}: {e}")
                        return app.id, None, str(e)
                    finally:
                        connection.close()

                # Parallel screening: up to 10 concurrent Gemini API calls
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {
                        executor.submit(screen_one, app): app
                        for app in apps_to_screen
                        if app.resume_url
                    }

                    if not futures:
                        print("[AI] No candidates with resume URLs found!")
                        errors.append("No candidates have uploaded resumes.")

                    for future in as_completed(futures):
                        try:
                            app_id, score, analysis_json = future.result(timeout=120)

                            # Ensure connection is alive for DB write
                            connection.ensure_connection()

                            with transaction.atomic():
                                app = JobApplication.objects.select_for_update().get(
                                    id=app_id
                                )
                                if score is not None:
                                    app.ai_score = score
                                    app.ai_analysis = analysis_json
                                    app.status = "REVIEWED"
                                    app.save()
                                    processed_count += 1
                                    print(
                                        f"[AI] ✅ Candidate {app.applicant.email} screened. Score: {score}"
                                    )
                                else:
                                    errors.append(
                                        f"{app.applicant.email}: {analysis_json}"
                                    )
                                    print(
                                        f"[AI] ❌ Candidate {app.applicant.email} failed: {analysis_json}"
                                    )

                            # Update progress in the report so frontend sees it
                            report.results["processed_count"] = processed_count
                            report.save(update_fields=["results"])
                        except Exception as e:
                            print(f"[AI] Future execution error: {e}")
                            errors.append(f"Execution error: {str(e)}")

                # Ensure connection for final query
                connection.ensure_connection()

                # Final Rankings Construction
                all_scored = (
                    JobApplication.objects.filter(
                        job=job, ai_score__isnull=False, is_deleted=False
                    )
                    .select_related("applicant")
                    .order_by("-ai_score")
                )
                results_data = []
                for rank, cand in enumerate(all_scored[:50], 1):
                    summary = ""
                    analysis_obj = None
                    try:
                        if cand.ai_analysis and cand.ai_analysis.strip().startswith(
                            "{"
                        ):
                            analysis_obj = json.loads(cand.ai_analysis)
                            summary = analysis_obj.get("recruiter_view", {}).get(
                                "explanation", ""
                            )
                    except:
                        pass
                    if not summary:
                        summary = (
                            (cand.ai_analysis[:500] + "...")
                            if cand.ai_analysis and len(cand.ai_analysis) > 500
                            else (cand.ai_analysis or "No analysis available.")
                        )

                    results_data.append(
                        {
                            "id": str(cand.id),
                            "rank": rank,
                            "name": f"{cand.applicant.first_name} {cand.applicant.last_name}",
                            "email": cand.applicant.email,
                            "score": cand.ai_score,
                            "summary": summary,
                            "analysis": analysis_obj,
                        }
                    )

                report.results = {
                    "status": "completed",
                    "job_id": str(job.id),
                    "processed_count": processed_count,
                    "total_applicants": all_scored.count(),
                    "top_candidates": results_data,
                    "errors": errors,
                }
                report.save()

                # AUTO-PROMOTION: Move the top-scoring candidate to INTERVIEW status automatically
                # This makes the AI agent truly autonomous and fast.
                if all_scored.exists():
                    top_candidate = all_scored.first()
                    # Only promote if they have a decent score (e.g., > 60)
                    if top_candidate.ai_score and top_candidate.ai_score >= 60:
                        print(
                            f"[AI] Auto-promoting top candidate {top_candidate.applicant.email} (Score: {top_candidate.ai_score}) to INTERVIEW."
                        )
                        top_candidate.status = "INTERVIEW"
                        top_candidate.save()

                        # Trigger orchestration for the interview session
                        try:
                            from AIrounds.services.orchestrator import (
                                InterviewOrchestrator,
                            )

                            InterviewOrchestrator.auto_orchestrate(top_candidate)
                        except Exception as e:
                            print(
                                f"[AI] Auto-orchestration failed for top candidate: {e}"
                            )

            except Exception as e:
                print(f"Background Screening Critical Error: {e}")
                if report:
                    try:
                        report.results["status"] = "failed"
                        report.results["error"] = str(e)
                        report.save()
                    except:
                        pass
            finally:
                connection.close()

        thread = threading.Thread(
            target=run_screening_background,
            args=(str(job.id), request.user.id, app_ids, str(report.id)),
        )
        thread.daemon = True
        thread.start()

        return self.build_response(
            "success",
            f"Screening started for {len(applications)} candidates.",
            {**report.results, "report_id": str(report.id)},
            status_code=status.HTTP_202_ACCEPTED,
        )


class DeleteScreeningReportView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def delete(self, request, report_id):
        try:
            report = AIScreeningReport.objects.get(
                id=report_id, recruiter=request.user, is_deleted=False
            )
            report.is_deleted = True
            report.save(update_fields=["is_deleted"])
            return self.build_response("success", "Report deleted.")
        except AIScreeningReport.DoesNotExist:
            return self.build_response(
                "error", "Report not found.", {}, status.HTTP_404_NOT_FOUND
            )
