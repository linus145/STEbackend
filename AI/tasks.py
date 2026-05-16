import json
import logging
from celery import shared_task
from django.db import connection, transaction
from django.contrib.auth import get_user_model
from jobs.models import JobApplication, JobPost
from AI.models import AIScreeningReport
from AI.services import AIService
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("ai.tasks")
User = get_user_model()

def screen_single_candidate(app_id, email, job_title, full_job_info, resume_url):
    """
    Helper function to screen a single candidate in a thread.
    """
    try:
        # This log will now appear for all candidates almost simultaneously
        logger.info(f"[AI Thread] Starting parallel screening for: {email}")
        
        score, analysis_json = AIService.analyze_resume(
            job_title, full_job_info, resume_url
        )
        return app_id, score, analysis_json
    except Exception as e:
        logger.error(f"[AI Thread] Error screening {email}: {e}")
        return app_id, None, str(e)
    finally:
        # Each thread must close its connection to avoid leaks
        connection.close()

@shared_task(bind=True)
def process_ai_screening(self, job_id, user_id, app_ids, report_id):
    """
    Celery task to handle background resume screening with parallel threads.
    """
    try:
        # Re-fetch objects in this task's context
        job = JobPost.objects.get(id=job_id)
        user = User.objects.get(id=user_id)
        report = AIScreeningReport.objects.get(id=report_id)
        
        apps_to_screen = list(
            JobApplication.objects.filter(id__in=app_ids).select_related("applicant")
        )

        logger.info(f"[AI Task] Parallel screening {len(apps_to_screen)} candidates for job: {job.title}")

        processed_count = 0
        errors = []
        job_skills = ", ".join([s.name for s in job.skills.all()])
        full_job_info = f"{job.description}\n\nREQUIRED SKILLS: {job_skills}"

        # 1. Parallel execution of AI analysis (The heavy I/O part)
        results_map = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_app = {
                executor.submit(
                    screen_single_candidate, 
                    app.id, app.applicant.email, job.title, full_job_info, app.resume_url
                ): app for app in apps_to_screen if app.resume_url
            }

            for future in as_completed(future_to_app):
                app = future_to_app[future]
                try:
                    app_id, score, analysis_json = future.result()
                    results_map[app_id] = (score, analysis_json)
                except Exception as exc:
                    logger.error(f"[AI Task] {app.applicant.email} generated an exception: {exc}")
                    errors.append(f"{app.applicant.email}: {str(exc)}")

        # 2. Sequential DB Updates (Ensures database integrity and avoids locks)
        for app in apps_to_screen:
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
        
        results_data = []
        for rank, cand in enumerate(all_scored[:50], 1):
            summary = ""
            analysis_obj = None
            try:
                if cand.ai_analysis and cand.ai_analysis.strip().startswith("{"):
                    analysis_obj = json.loads(cand.ai_analysis)
                    summary = analysis_obj.get("recruiter_view", {}).get("explanation", "")
            except:
                pass
            
            if not summary:
                summary = (
                    (cand.ai_analysis[:500] + "...")
                    if cand.ai_analysis and len(cand.ai_analysis) > 500
                    else (cand.ai_analysis or "No analysis available.")
                )

            results_data.append({
                "id": str(cand.id),
                "rank": rank,
                "name": f"{cand.applicant.first_name} {cand.applicant.last_name}",
                "email": cand.applicant.email,
                "score": cand.ai_score,
                "summary": summary,
                "analysis": analysis_obj,
            })

        report.results = {
            "status": "completed",
            "job_id": str(job.id),
            "processed_count": processed_count,
            "total_applicants": all_scored.count(),
            "top_candidates": results_data,
            "errors": errors,
        }
        report.save()

        # AUTO-PROMOTION: Move top candidate to INTERVIEW
        if all_scored.exists():
            top_candidate = all_scored.first()
            if top_candidate.ai_score and top_candidate.ai_score >= 60:
                logger.info(f"[AI Task] Auto-promoting top candidate {top_candidate.applicant.email} to INTERVIEW.")
                top_candidate.status = "INTERVIEW"
                top_candidate.save()
                
                try:
                    from AIrounds.services.orchestrator import InterviewOrchestrator
                    InterviewOrchestrator.auto_orchestrate(top_candidate)
                except Exception as e:
                    logger.error(f"[AI Task] Auto-orchestration failed: {e}")

        return report.results

    except Exception as e:
        logger.error(f"Critical error in process_ai_screening: {e}")
        try:
            report = AIScreeningReport.objects.get(id=report_id)
            report.results["status"] = "failed"
            report.results["error"] = str(e)
            report.save()
        except:
            pass
        raise e
