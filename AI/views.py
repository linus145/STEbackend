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
        applications = list(job.applications.filter(status__in=["PENDING", "REVIEWED"], is_deleted=False))
        app_ids = [str(app.id) for app in applications]
        if not applications:
            all_scored_qs = job.applications.filter(
                ai_score__isnull=False, is_deleted=False
            ).order_by("-ai_score")
            total_scored = all_scored_qs.count()

            if total_scored > 0:
                # Fetch and self-heal mismatching database scores on-the-fly
                all_scored_list = list(all_scored_qs[:25])
                for cand in all_scored_list:
                    summary, analysis_obj = AIService.extract_summary_and_analysis(cand.ai_analysis)
                    if analysis_obj and isinstance(analysis_obj, dict):
                        rv_score = analysis_obj.get("recruiter_view", {}).get("match_score")
                        if rv_score is not None:
                            try:
                                parsed_score = int(rv_score)
                                if parsed_score != cand.ai_score:
                                    cand.ai_score = parsed_score
                                    cand.save(update_fields=["ai_score"])
                            except:
                                pass

                # Sort by corrected score descending (primary) and skills match percentage (secondary) to update priorities/rankings
                all_scored_list.sort(key=lambda c: (c.ai_score or 0, AIService.get_skills_match_pct(c.ai_analysis)), reverse=True)

                results_data = []
                for rank, cand in enumerate(all_scored_list, 1):
                    summary, analysis_obj = AIService.extract_summary_and_analysis(cand.ai_analysis)

                    results_data.append(
                        {
                            "id": str(cand.id),
                            "rank": rank,
                            "name": f"{cand.applicant.first_name} {cand.applicant.last_name}",
                            "email": cand.applicant.email,
                            "score": cand.ai_score,
                            "summary": summary,
                            "analysis": analysis_obj,
                            "pipeline_disposition": (
                                analysis_obj.get("recruiter_view", {}).get("pipeline_disposition", "")
                                if analysis_obj else ""
                            ),
                            "knockout_applied": (
                                analysis_obj.get("recruiter_view", {}).get("knockout_applied", False)
                                if analysis_obj else False
                            ),
                            "knockout_reason": (
                                analysis_obj.get("recruiter_view", {}).get("knockout_reason", "")
                                if analysis_obj else ""
                            ),
                            "hiring_confidence": (
                                analysis_obj.get("recruiter_view", {}).get("hiring_confidence", "")
                                if analysis_obj else ""
                            ),
                            "recruiter_action_memo": (
                                analysis_obj.get("recruiter_view", {}).get("recruiter_action_memo", "")
                                if analysis_obj else ""
                            ),
                            "skills_match_pct": (
                                analysis_obj.get("intelligence", {}).get("skills_assessment", {}).get("skills_match_percentage", 0)
                                if analysis_obj else 0
                            ),
                            "career_level": (
                                analysis_obj.get("intelligence", {}).get("career_summary", {}).get("career_level_assessed", "")
                                if analysis_obj else ""
                            ),
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
                "No applications found to screen.",
                {},
                status.HTTP_400_BAD_REQUEST,
            )

        # 2. Prevent Multiple Concurrent Screenings (with stale check)
        from django.utils import timezone
        from datetime import timedelta

        ten_minutes_ago = timezone.now() - timedelta(minutes=10)
        existing_report = AIScreeningReport.objects.filter(
            job_id=job.id, results__status="processing", is_deleted=False
        ).first()

        # If a report is processing but older than 10 min, it's likely stuck — allow restart
        is_stale = existing_report and existing_report.created_at < ten_minutes_ago

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

        # 3. Extract & Validate Model
        model = request.data.get("model", "gemini-2.5-flash-lite").strip()
        allowed_models = [
            "kimi",
            "Kimi-K2.6",
            "grok",
            "grok-4-20-non-reasoning",
            "grok-4.1-non-reasoning",
            "gemini-3.5-flash",
            "gemini-3.5-flash-live",
            "gemini-3.0-flash-live",
            "gemini-3.1-pro-preview",
            "gemini-3.1-flash-lite",
            "gemini-3-pro-preview",
            "gemini-3-flash-preview",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-2.0-flash-thinking-exp",
            "gemini-2.0-pro-exp",
            "text-multilingual-embedding-002"
        ]
        if model not in allowed_models:
            model = "gemini-2.5-flash-lite"

        # Check and burn credits
        credits_to_burn = len(applications)
        try:
            from creditsystem.utils import burn_credits
            burn_credits(
                request.user, 
                credits_to_burn, 
                f"AI resume screening for {credits_to_burn} candidates on job: {job.title}",
                module="resume_screening",
                job_id=str(job.id),
                action_type="bulk_resume_screening",
                metadata={
                    "candidates_count": credits_to_burn,
                    "application_ids": [str(aid) for aid in app_ids]
                }
            )
        except Exception as e:
            return self.build_response(
                "error", f"Credit verification failed: {str(e)}", {}, status.HTTP_403_FORBIDDEN
            )

        # 4. Create Processing Report
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
                "model_used": model,
            },
        )

        # FAST STATUS UPDATE: Update all targeted apps to REVIEWED immediately
        # so the agent can see the state change without waiting for the AI thread.
        # This prevents sync delays for the autonomous agent.
        JobApplication.objects.filter(id__in=app_ids, status="PENDING").update(
            status="REVIEWED"
        )

        # 5. Trigger Celery Task
        from AI.tasks import process_ai_screening

        task = process_ai_screening.delay(
            str(job.id), request.user.id, app_ids, str(report.id), model=model
        )
        report.results["task_id"] = task.id
        report.results["app_ids"] = app_ids
        report.save(update_fields=["results"])

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
            
            # Revoke the Celery task if it is still processing
            if report.results and report.results.get("status") == "processing":
                task_id = report.results.get("task_id")
                if task_id:
                    try:
                        from maincore.celery import app as celery_app
                        celery_app.control.revoke(task_id, terminate=True)
                        print(f"[AI] Revoked Celery task: {task_id}")
                    except Exception as e:
                        print(f"[AI] Failed to revoke Celery task: {e}")

                # Restore applications that haven't been scored yet back to PENDING status
                app_ids = report.results.get("app_ids")
                if app_ids:
                    JobApplication.objects.filter(
                        id__in=app_ids,
                        ai_score__isnull=True,
                        status="REVIEWED"
                    ).update(status="PENDING")

                # Set status to failed/cancelled in results so it doesn't block future checks
                report.results["status"] = "failed"
                report.results["error"] = "Cancelled by user"

            report.is_deleted = True
            report.save(update_fields=["is_deleted", "results"])
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
        selected_model = request.data.get("model", "gemini-2.5-flash-lite").strip()
        allowed_models = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro"
        ]
        if selected_model not in allowed_models:
            selected_model = "gemini-2.5-flash-lite"

        if not user_message:
            return self.build_response("error", "Message is required.", {}, status.HTTP_400_BAD_REQUEST)

        candidate_context = request.data.get("candidate_context", None)
        candidate_id = None
        if candidate_context and isinstance(candidate_context, dict):
            candidate_id = candidate_context.get("id")


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

        # Dynamic Candidate Context Parsing & Injection
        candidate_context = request.data.get("candidate_context", None)
        context_str = ""
        if candidate_context and isinstance(candidate_context, dict):
            context_str = (
                f"You are currently discussing candidate '{candidate_context.get('name')}' for this job position.\n"
                f"Candidate Screening Metadata:\n"
                f"- Match/Fit Score: {candidate_context.get('score')}%\n"
                f"- Summary: {candidate_context.get('summary')}\n"
            )
            if candidate_context.get('strengths'):
                context_str += f"- Strengths: {', '.join(candidate_context.get('strengths'))}\n"
            if candidate_context.get('concerns'):
                context_str += f"- Concerns: {', '.join(candidate_context.get('concerns'))}\n"
            if candidate_context.get('missing_skills'):
                context_str += f"- Missing required skills: {', '.join(candidate_context.get('missing_skills'))}\n"
            if candidate_context.get('knockout_reason'):
                context_str += f"- Knockout details: {candidate_context.get('knockout_reason')}\n"
            context_str += "\nUse this context when answering the user's questions about this candidate. Keep answers very brief, specific, and professional.\n\n"

        try:
            from Ahrmagent1.services.llm_planner import APP_KNOWLEDGE
            client = _get_client(api_key)

            # Build authentic system instruction with strict character limit and application knowledge
            system_instruction = (
                "You are an expert conversational AI agent embedded inside an HR & Recruitment Operating System. "
                "You are here to answer questions, explain processes, and describe settings inside this application. "
                "Here is the knowledge about the application structure, settings, navigation, and workflows:\n"
                f"{APP_KNOWLEDGE}\n\n"
                f"{context_str}"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Answer questions about the application structure, configurations, settings (such as grace period, attendance, payroll) and workflows using the knowledge above.\n"
                "2. If candidate screening context is provided, prioritize answering questions specifically about that candidate's qualifications, fit score, strengths, and weaknesses.\n"
                "3. Do NOT output Playwright actions or structured JSON. Answer naturally in conversational text.\n"
                "4. Your output must be highly concise, direct, and strictly under 500 characters in total length.\n"
                "5. Avoid excessively long pleasantries. Be authentic, natural, and extremely brief. Do not exceed 500 characters."
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
                model=selected_model,
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
