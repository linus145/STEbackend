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

from django.conf import settings
from google.genai import types
from AI.models import AIScreeningReport
from AI.serializers import AIScreeningReportSerializer
from AI.services import AIService, _get_client

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


from subscription.utils import HasAIScreeningPermission

class AnalyzeResumesView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated, HasAIScreeningPermission)

    def post(self, request, job_id):
        try:
            job = JobPost.objects.select_related("company").get(id=job_id)
        except JobPost.DoesNotExist:
            return self.build_response(
                "error", "Job post not found.", {}, status.HTTP_404_NOT_FOUND
            )

        if not hasattr(request.user, "company_profile") or job.company != request.user.company_profile:
            return self.build_response(
                "error", "Unauthorized access to job post.", {}, status.HTTP_403_FORBIDDEN
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

        # 4. Trigger Celery Task
        from AI.tasks import process_ai_screening

        process_ai_screening.delay(
            str(job.id), request.user.id, app_ids, str(report.id)
        )

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


class AIPlanChatView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user_message = request.data.get("message", "").strip()
        history = request.data.get("history", [])

        if not user_message:
            return self.build_response("error", "Message is required.", {}, status.HTTP_400_BAD_REQUEST)

        # 1. Prompt Injection Protection & Input Sanitization
        injection_keywords = [
            "ignore previous instructions", "ignore all previous", "system prompt",
            "developer mode", "you are now a", "jailbreak", "override instructions",
            "forget your instructions", "bypass limit", "expose knowledge"
        ]
        message_lower = user_message.lower()
        if any(keyword in message_lower for keyword in injection_keywords) or len(user_message) > 1000:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Potential prompt injection or oversized message detected from user: {request.user.email}")
            return self.build_response(
                "success", 
                "Reply generated.", 
                {"reply": "I'm sorry, but I can only answer questions about recruitment, applicant settings, and standard HR workflows."}
            )

        api_key = getattr(settings, "GEMINI_API_KEY", None)
        if not api_key:
            # Standalone fallback hiring strategy
            fallback_text = (
                "I have compiled a custom hiring strategy for you:\n\n"
                "1. Target matches on GitHub and LinkedIn with active profiles.\n"
                "2. Filter candidates based on required technical skill matrices.\n"
                "3. Send invitation rounds using AI Interviews.\n\n"
                "Let me know if you would like me to configure specific questions!"
            )
            return self.build_response("success", "Reply generated (Fallback).", {"reply": fallback_text})

        try:
            from Ahrmagent1.services.llm_planner import APP_KNOWLEDGE
            client = _get_client(api_key)

            # Build authentic system instruction with strict character limit and application knowledge
            system_instruction = (
                "You are an expert conversational AI agent embedded inside an HR & Recruitment Operating System. "
                "You are here to answer questions, explain processes, and describe settings inside this application. "
                "Here is the knowledge about the application structure, settings, navigation, and workflows:\n"
                f"{APP_KNOWLEDGE}\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Answer questions about the application structure, configurations, settings (such as grace period, attendance, payroll) and workflows using the knowledge above.\n"
                "2. Do NOT output Playwright actions or structured JSON. Answer naturally in conversational text.\n"
                "3. Your output must be highly concise, direct, and strictly under 500 characters in total length.\n"
                "4. Avoid excessively long pleasantries. Be authentic, natural, and extremely brief. Do not exceed 500 characters."
            )

            # Format history
            contents = []
            for item in history:
                role = "user" if item.get("sender") == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=item.get("text", ""))]
                    )
                )

            # Add current user message
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_message)]
                )
            )

            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    max_output_tokens=150,  # Limits token footprint to strict character boundary (~125-150 tokens)
                    temperature=0.7,
                ),
            )

            if response and response.text:
                # Enforce absolute 500 character constraint on string slicing
                reply = response.text[:500].strip()
            else:
                reply = "I couldn't process that. Let's try formulating another strategy!"

            return self.build_response("success", "Reply generated.", {"reply": reply})

        except Exception as e:
            print(f"[AI Chat] Error: {e}")
            fallback_text = (
                "I have compiled a custom hiring strategy for you:\n\n"
                "1. Target matches on GitHub and LinkedIn with active profiles.\n"
                "2. Filter candidates based on required technical skill matrices.\n"
                "3. Send invitation rounds using AI Interviews.\n\n"
                "Let me know if you would like me to configure specific questions!"
            )
            return self.build_response("success", "Reply generated (Fallback on error).", {"reply": fallback_text})
