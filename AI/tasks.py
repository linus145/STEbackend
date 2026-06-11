import json
import logging
from celery import shared_task
from django.db import connection, transaction
from django.contrib.auth import get_user_model
from jobs.models import JobApplication, JobPost
from AI.models import AIScreeningReport
from AI.services import AIService
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED

import threading
import ctypes

logger = logging.getLogger("ai.tasks")
User = get_user_model()

# Global registry of active threads per report_id
_active_threads_by_report = {}
_threads_lock = threading.Lock()

def register_thread(report_id, thread_id):
    if not report_id:
        return
    with _threads_lock:
        if report_id not in _active_threads_by_report:
            _active_threads_by_report[report_id] = set()
        _active_threads_by_report[report_id].add(thread_id)

def unregister_thread(report_id, thread_id):
    if not report_id:
        return
    with _threads_lock:
        if report_id in _active_threads_by_report:
            _active_threads_by_report[report_id].discard(thread_id)
            if not _active_threads_by_report[report_id]:
                del _active_threads_by_report[report_id]

def kill_threads_for_report(report_id):
    if not report_id:
        return
    with _threads_lock:
        threads = list(_active_threads_by_report.pop(report_id, []))
    for tid in threads:
        try:
            # Raise SystemExit exception in the target thread
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), ctypes.py_object(SystemExit))
            logger.info(f"[AI] Sent SystemExit exception to thread {tid} for report {report_id}")
        except Exception as e:
            logger.error(f"[AI] Error killing thread {tid}: {e}")

def screen_single_candidate(app_id, email, job_title, job_brief, resume_url, model=None, report_id=None):
    """
    Helper function to screen a single candidate in a thread.
    job_brief is a structured dict with all ATS criteria.
    """
    tid = threading.get_ident()
    register_thread(report_id, tid)
    try:
        if report_id:
            from AI.models import AIScreeningReport
            try:
                if not AIScreeningReport.objects.filter(id=report_id, is_deleted=False).exists():
                    logger.info(f"[AI Thread] Report {report_id} has been cancelled/deleted. Aborting Gemini call for {email}.")
                    return app_id, None, "Cancelled"
            except Exception as db_err:
                logger.warning(f"[AI Thread] Could not check report status in thread: {db_err}")

        logger.info(f"[AI Thread] Starting strict ATS screening for: {email} using model: {model}")
        score, analysis_json = AIService.analyze_resume(
            job_title, job_brief, resume_url, selected_model=model, report_id=report_id
        )
        return app_id, score, analysis_json
    except SystemExit:
        logger.info(f"[AI Thread] Thread for {email} was aborted due to cancellation.")
        return app_id, None, "Cancelled"
    except Exception as e:
        logger.error(f"[AI Thread] Error screening {email}: {e}")
        return app_id, None, str(e)
    finally:
        unregister_thread(report_id, tid)
        # Each thread must close its connection to avoid leaks
        connection.close()

@shared_task(bind=True)
def process_ai_screening(self, job_id, user_id, app_ids, report_id, model=None):
    """
    Celery task to handle background resume screening with parallel threads.
    """
    try:
        # Re-fetch objects in this task's context
        job = JobPost.objects.get(id=job_id)
        user = User.objects.get(id=user_id)
        report = AIScreeningReport.objects.get(id=report_id)

        # Safeguard: if report is already completed, do not execute duplicate screening
        if report.results and report.results.get("status") == "completed":
            logger.info(f"[AI Task] Report {report_id} is already completed. Skipping screening task.")
            return report.results

        
        apps_to_screen = list(
            JobApplication.objects.filter(id__in=app_ids).select_related("applicant")
        )

        logger.info(f"[AI Task] Parallel screening {len(apps_to_screen)} candidates for job: {job.title} using model: {model}")

        processed_count = 0
        errors = []

        # Build comprehensive structured job brief for strict ATS scoring
        job_skills_list = [s.name for s in job.skills.all()]
        job_brief = {
            "description": job.description,
            "required_skills": ", ".join(job_skills_list) if job_skills_list else "Not specified",
            "experience_level": job.experience_level,  # ENTRY / MID / SENIOR / LEAD
            "job_type": job.job_type,                  # FULL_TIME / PART_TIME / CONTRACT / INTERNSHIP
            "work_mode": job.work_mode,                # REMOTE / ONSITE / HYBRID
            "department": job.department or "",
            "salary_min": str(job.salary_min) if job.salary_min else "",
            "salary_max": str(job.salary_max) if job.salary_max else "",
            "currency": job.currency or "INR",
            "job_category": job.job_category,
        }

        logger.info(
            f"[AI Task] Job brief — title='{job.title}' | level={job.experience_level} | "
            f"skills=[{', '.join(job_skills_list[:5])}{'...' if len(job_skills_list) > 5 else ''}] | "
            f"type={job.job_type} | mode={job.work_mode}"
        )

        # 1. Parallel execution of AI analysis (The heavy I/O part)
        results_map = {}
        cancelled = False
        executor = ThreadPoolExecutor(max_workers=30)
        try:
            future_to_app = {
                executor.submit(
                    screen_single_candidate,
                    app.id, app.applicant.email, job.title, job_brief, app.resume_url, model, report.id
                ): app for app in apps_to_screen if app.resume_url
            }

            futures_list = list(future_to_app.keys())
            while futures_list:
                # Active Cancellation check:
                from django.db import connection
                connection.close()
                if not AIScreeningReport.objects.filter(id=report_id, is_deleted=False).exists():
                    logger.info(f"[AI Task] Report {report_id} has been cancelled by user. Aborting task execution.")
                    cancelled = True
                    kill_threads_for_report(report_id)
                    executor.shutdown(wait=False, cancel_futures=True)
                    JobApplication.objects.filter(id__in=app_ids, ai_score__isnull=True).update(status="PENDING")
                    return {"status": "cancelled"}

                done, not_done = wait(futures_list, timeout=1.0, return_when=FIRST_COMPLETED)
                for future in done:
                    futures_list.remove(future)
                    app = future_to_app[future]
                    try:
                        app_id, score, analysis_json = future.result()
                        results_map[app_id] = (score, analysis_json)
                    except Exception as exc:
                        logger.error(f"[AI Task] {app.applicant.email} generated an exception: {exc}")
                        errors.append(f"{app.applicant.email}: {str(exc)}")
        finally:
            if not cancelled:
                executor.shutdown(wait=True)

        # 2. Sequential DB Updates (Ensures database integrity and avoids locks)
        for app in apps_to_screen:
            from django.db import connection
            connection.close()
            if not AIScreeningReport.objects.filter(id=report_id, is_deleted=False).exists():
                logger.info(f"[AI Task] Report {report_id} has been cancelled by user during DB updates. Aborting.")
                JobApplication.objects.filter(id__in=app_ids, ai_score__isnull=True).update(status="PENDING")
                return {"status": "cancelled"}

            if app.id not in results_map:
                continue
            
            score, analysis_json = results_map[app.id]
            
            try:
                self.update_state(state='PROGRESS', meta={'current': processed_count, 'total': len(apps_to_screen)})
                
                with transaction.atomic():
                    app_db = JobApplication.objects.select_for_update().get(id=app.id)
                    if score is not None:
                        app_db.ai_score = score
                        app_db.ai_analysis = analysis_json
                        app_db.status = "REVIEWED"
                        app_db.save()
                        processed_count += 1
                        logger.info(f"[AI Task] Saved result for: {app_db.applicant.email} (Score: {score})")
                    else:
                        errors.append(f"{app_db.applicant.email}: {analysis_json}")
                        logger.error(f"[AI Task] Result failed for: {app_db.applicant.email}")
                        app_db.status = "PENDING"
                        app_db.save()

                # Update progress in the report for frontend visibility
                report.results["processed_count"] = processed_count
                report.save(update_fields=["results"])
                
            except Exception as e:
                logger.error(f"[AI Task] DB Update Error for {app.applicant.email}: {e}")
                errors.append(f"{app.applicant.email}: {str(e)}")

        # 3. Final Rankings Construction
        all_scored = (
            JobApplication.objects.filter(
                job=job, ai_score__isnull=False, is_deleted=False
            )
            .select_related("applicant")
            .order_by("-ai_score")
        )
        
        # Fetch and self-heal mismatching database scores on-the-fly
        all_scored_list = list(all_scored[:50])
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

            # Safe access helpers
            rv = analysis_obj.get("recruiter_view", {}) if analysis_obj else {}
            intel = analysis_obj.get("intelligence", {}) if analysis_obj else {}

            results_data.append({
                "id": str(cand.id),
                "rank": rank,
                "name": f"{cand.applicant.first_name} {cand.applicant.last_name}",
                "email": cand.applicant.email,
                "score": cand.ai_score,
                "summary": summary,
                "analysis": analysis_obj,
                # ─── Core recruiter view fields ───────────────────
                "pipeline_disposition": rv.get("pipeline_disposition", ""),
                "knockout_applied": rv.get("knockout_applied", False),
                "knockout_reason": rv.get("knockout_reason", ""),
                "hiring_confidence": rv.get("hiring_confidence", ""),
                "recruiter_action_memo": rv.get("recruiter_action_memo", ""),
                "skills_match_pct": intel.get("skills_assessment", {}).get("skills_match_percentage", 0),
                "career_level": intel.get("career_summary", {}).get("career_level_assessed", ""),
                # ─── 20-Dimension enriched fields ─────────────────
                "recommendation": rv.get("recommendation", ""),
                "recommendation_reason": rv.get("recommendation_reason", ""),
                "score_breakdown": rv.get("score_breakdown", {}),
                "score_weights": rv.get("score_weights", {}),
                "resume_completeness": intel.get("resume_completeness", {}).get("total_score", 0),
                "resume_completeness_detail": intel.get("resume_completeness", {}),
                "professional_summary_quality": intel.get("professional_summary", {}).get("quality", ""),
                "job_stability_score": intel.get("job_stability", {}).get("stability_score", 0),
                "job_stability": intel.get("job_stability", {}),
                "keyword_match_pct": intel.get("keyword_match", {}).get("keyword_match_percentage", 0),
                "keyword_match": intel.get("keyword_match", {}),
                "missing_keywords": intel.get("missing_keywords", []),
                "role_fit": intel.get("role_fit", {}),
                "industry_experience": intel.get("industry_experience", {}),
                "career_progression": intel.get("career_progression", {}),
                "career_growth_score": intel.get("career_progression", {}).get("career_growth_score", 0),
                "achievements": intel.get("achievements", []),
                "resume_quality_score": intel.get("resume_quality", {}).get("resume_quality_score", 0),
                "resume_quality": intel.get("resume_quality", {}),
            })

        report.results = {
            "status": "completed",
            "job_id": str(job.id),
            "processed_count": processed_count,
            "total_applicants": all_scored.count(),
            "top_candidates": results_data,
            "errors": errors,
            "model_used": model,
        }
        report.save()

        # ── AUTO-PROMOTION: Use AI's recommendation or programmatic fallback ──
        # Only SHORTLIST, STRONG_HIRE or score >= 90 triggers immediate promotion
        # to INTERVIEW + orchestration.
        if all_scored.exists():
            top_candidate = all_scored.first()
            if top_candidate.ai_score is not None:
                disposition = ""
                recommendation = ""
                try:
                    if top_candidate.ai_analysis and top_candidate.ai_analysis.strip().startswith("{"):
                        a_obj = json.loads(top_candidate.ai_analysis)
                        rv = a_obj.get("recruiter_view", {})
                        disposition = rv.get("pipeline_disposition", "")
                        recommendation = rv.get("recommendation", "")
                except Exception:
                    pass

                # Promote if AI says SHORTLIST, recommendation is STRONG_HIRE, or score >= 90
                should_promote = (
                    disposition == "SHORTLIST"
                    or recommendation == "STRONG_HIRE"
                    or top_candidate.ai_score >= 90
                )

                if should_promote:
                    logger.info(
                        f"[AI Task] Auto-promoting top candidate {top_candidate.applicant.email} "
                        f"to INTERVIEW — disposition={disposition or 'N/A'}, recommendation={recommendation or 'N/A'}, score={top_candidate.ai_score}"
                    )
                    top_candidate.status = "INTERVIEW"
                    top_candidate.save()

                    try:
                        from AIrounds.services.orchestrator import InterviewOrchestrator
                        InterviewOrchestrator.auto_orchestrate(top_candidate)
                    except Exception as e:
                        logger.error(f"[AI Task] Auto-orchestration failed: {e}")
                else:
                    logger.info(
                        f"[AI Task] Top candidate NOT promoted — "
                        f"disposition={disposition or 'N/A'}, recommendation={recommendation or 'N/A'}, score={top_candidate.ai_score}"
                    )

        return report.results

    except Exception as e:
        logger.error(f"Critical error in process_ai_screening: {e}")
        try:
            report = AIScreeningReport.objects.get(id=report_id)
            report.results["status"] = "failed"
            report.results["error"] = str(e)
            report.results["model_used"] = model
            report.save()

            # Restore applications that haven't been scored yet back to PENDING status
            if app_ids:
                JobApplication.objects.filter(
                    id__in=app_ids,
                    ai_score__isnull=True,
                    status="REVIEWED"
                ).update(status="PENDING")
        except Exception as db_err:
            logger.error(f"Failed to restore application statuses on task failure: {db_err}")
        raise e
