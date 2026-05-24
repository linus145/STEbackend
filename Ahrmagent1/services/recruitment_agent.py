from Ahrmagent1.services.browser_agent import BrowserAgentService
import asyncio
from django.conf import settings
from asgiref.sync import sync_to_async
from jobs.models import JobPost, JobApplication


class RecruitmentAgentService(BrowserAgentService):
    """
    Specific agent for HR and Recruitment workflows.
    Extends BrowserAgent with recruitment-specific logic.
    """

    async def create_job_workflow(self, job_data, use_existing=False):
        """
        Flow for starting from scratch or re-using a session.
        """
        try:
            # 1. Start (use_existing=True will connect to port 9222)
            await self.start_browser(
                headless=False, slow_mo=2000, use_existing=use_existing
            )

            # Check if we are already logged in
            current_url = self.page.url
            self.log(f"Current page: {current_url}")

            if "login" in current_url or settings.FRONTEND_URL not in current_url:
                # 2. Login (Only if we are NOT already logged in)
                self.log("Not logged in. Navigating to login page...")
                await self.navigate(f"{settings.FRONTEND_URL}/login")

                # Check again if we redirected to dashboard automatically (if persistent)
                if "dashboard" not in self.page.url:
                    await self.fill_field("input#email", "founder1@gmail.com")
                    await self.fill_field("input#password", "Founder1@gmail.com")
                    await self.click_element("button[type='submit']")

                    # Wait for dashboard to load
                    await self.page.wait_for_url("**/dashboard**", timeout=10000)
                    self.log("Logged in and reached dashboard")
                else:
                    self.log("Automatically logged in via session")
            else:
                self.log("Already on a logged-in page")

            # 3. Handle Navigation to Recruiter Dashboard
            current_url = self.page.url
            recruiter_page = self.page

            if "/recruiter" not in current_url:
                # We are likely on the main dashboard, need to click 'Hire with AI'
                self.log("Finding 'Hire with AI' link...")
                async with self.context.expect_page() as new_page_info:
                    # We look for a link that contains "Hire with AI" text
                    await self.page.click("text=Hire with AI")

                recruiter_page = await new_page_info.value
                await recruiter_page.wait_for_load_state("networkidle")
                self.log("Switched to Recruiter Dashboard tab")
            else:
                self.log("Already on Recruiter Dashboard")

            # 4. Navigate to 'Jobs' tab in recruiter header
            self.log("Checking if on 'Jobs' section...")
            if "/jobs" not in recruiter_page.url:
                self.log("Navigating to 'Jobs' section...")
                await recruiter_page.click("text=Jobs")
                await asyncio.sleep(1)  # Small wait for tab content
            else:
                self.log("Already on Jobs section")

            # 5. Click 'AI Job Post' button
            self.log("Clicking 'AI Job Post' button...")
            await recruiter_page.click("text=AI Job Post")
            await asyncio.sleep(1)

            # 6. Fill AI Prompt
            self.log("Filling AI Prompt...")
            prompt = job_data.get(
                "prompt",
                f"Post a job for a {job_data.get('title', 'Senior Software Engineer')} in Bangalore. We need someone with 5+ years of experience in React and Node.js. Competitive salary and remote options available.",
            )
            await recruiter_page.fill("textarea", prompt)

            # 7. Click 'Run Agent'
            self.log("Running AI Agent...")
            await recruiter_page.click("text=Run Agent")

            # 8. Wait for completion (look for 'Agent is working' to disappear or success message)
            self.log("Waiting for Agent to finish...")
            # We can wait for the 'Run Agent' text to reappear or a success toast
            await recruiter_page.wait_for_selector(
                "text=AI Agent successfully posted the job!", timeout=60000
            )

            # 9. Take final screenshot
            old_page = self.page
            self.page = recruiter_page
            await self.take_screenshot(name="job_posted_success")
            self.page = old_page

            self.log("Workflow completed successfully", action="workflow_complete")
            return True

        except Exception as e:
            self.log(
                f"Workflow failed: {str(e)}", level="ERROR", action="workflow_error"
            )
            # If we have a recruiter_page, try taking screenshot there
            try:
                await self.take_screenshot(name="error_state")
            except:
                pass
            raise e
        finally:
            if not use_existing:
                await self.close_browser()
            else:
                await self.stop_playwright()
                self.log("Leaving browser open for user handover")

    async def execute_full_hiring_workflow(
        self, job_id, target_count, use_existing=False, recruiter_user_id=None
    ):
        """
        Pure Backend autonomous workflow.
        No browser needed! This interacts directly with Services and DB.
        """
        try:
            from AI.views import AnalyzeResumesView
            from AI.services import AIService

            # 1. Monitoring Phase
            self.log(
                f"Starting browserless monitoring for Job ID: {job_id} (Target: {target_count})",
                action="start_monitoring",
            )

            while True:
                job = await sync_to_async(JobPost.objects.get, thread_sensitive=False)(
                    id=job_id
                )
                count = await sync_to_async(
                    lambda: job.applications.count(), thread_sensitive=False
                )()

                self.log(f"Backend Monitor: Job '{job.title}' has {job.open_positions} open positions. Found {count} applications out of target {target_count} for screening.")

                if count >= target_count:
                    self.log(
                        f"Target count reached. Triggering AI Screening Engine for {count} applications (Job Openings: {job.open_positions})...",
                        action="trigger_screening",
                    )
                    break

                # Wait 30 seconds before checking again (faster than 60)
                await asyncio.sleep(30)

            # 2. Screening Phase (Direct Service Call)
            self.log(
                "AI Screening started in background...", action="screening_running"
            )

            # We pre-fetch 'applicant' to avoid 'async context' errors when accessing emails/names
            def get_pending():
                return list(
                    JobApplication.objects.filter(
                        job_id=job_id, status="PENDING", is_deleted=False
                    ).select_related("applicant")
                )

            pending_apps = await sync_to_async(get_pending, thread_sensitive=False)()

            if not pending_apps:
                self.log("No pending applicants to screen. Proceeding to selection.")
            else:
                self.log(f"Screening {len(pending_apps)} candidates in parallel via Gemini...")

                job_skills = await sync_to_async(
                    lambda: ", ".join([s.name for s in job.skills.all()]),
                    thread_sensitive=False,
                )()
                full_job_info = f"{job.description}\n\nREQUIRED SKILLS: {job_skills}"
                job_title = job.title

                # Run all screenings in parallel using ThreadPoolExecutor
                def run_parallel_screening(apps, j_title, j_info):
                    from concurrent.futures import ThreadPoolExecutor, as_completed
                    from django.db import connection as db_conn

                    def screen_one(app_id, app_email, resume_url):
                        db_conn.close()
                        try:
                            score, analysis_json = AIService.analyze_resume(j_title, j_info, resume_url)
                            return app_id, app_email, score, analysis_json
                        except Exception as e:
                            return app_id, app_email, None, str(e)
                        finally:
                            db_conn.close()

                    results = []
                    # Up to 10 parallel Gemini API calls
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        futures = {
                            executor.submit(screen_one, a.id, a.applicant.email, a.resume_url): a
                            for a in apps if a.resume_url
                        }
                        for future in as_completed(futures):
                            try:
                                results.append(future.result(timeout=120))
                            except Exception as e:
                                app = futures[future]
                                results.append((app.id, app.applicant.email, None, str(e)))
                    return results

                screening_results = await sync_to_async(
                    run_parallel_screening, thread_sensitive=False
                )(pending_apps, job_title, full_job_info)

                # Now update all applications with their scores
                processed = 0
                for app_id, app_email, score, analysis_json in screening_results:
                    try:
                        def update_app(a_id, s, aj):
                            from jobs.models import JobApplication
                            a = JobApplication.objects.get(id=a_id)
                            a.ai_score = s
                            a.ai_analysis = aj
                            a.status = "REVIEWED"
                            a.save()

                        await sync_to_async(update_app, thread_sensitive=False)(
                            app_id, score, analysis_json
                        )
                        processed += 1
                        self.log(f"Score for {app_email}: {score}%")
                    except Exception as e:
                        self.log(f"Failed to save score for {app_email}: {str(e)}", level="WARNING")

                self.log(
                    f"AI Screening complete. {processed} candidates processed.",
                    action="screening_complete",
                )

            # 3. Shortlisting Phase
            open_positions = job.open_positions if (job.open_positions and job.open_positions > 0) else 1
            self.log(f"Picking the top {open_positions} scorer(s) for interview...", action="shortlisting")

            def get_top_n(n):
                return list(
                    JobApplication.objects.filter(job_id=job_id, ai_score__isnull=False)
                    .select_related("applicant")
                    .order_by("-ai_score")[:n]
                )

            top_apps = await sync_to_async(get_top_n, thread_sensitive=False)(open_positions)

            if not top_apps:
                self.log(
                    "No candidates found with scores. Workflow ended.", level="ERROR"
                )
                return False

            self.log(f"Top candidate(s) shortlisted: " + ", ".join([f"{app.applicant.email} ({app.ai_score}%)" for app in top_apps]))

            # 4. Action Phase: Mark as Interview
            self.log(
                f"Transitioning {len(top_apps)} shortlisted candidate(s) to Interview stage...",
                action="interview_transition",
            )

            def final_actions(app_ids, j_id, r_user_id):
                from jobs.models import JobApplication, JobPost
                from AI.models import AIScreeningReport
                from django.contrib.auth import get_user_model
                import json

                User = get_user_model()

                # Mark all top application(s) as interview
                apps = list(JobApplication.objects.select_related("job", "job__company", "job__company__owner").filter(
                    id__in=app_ids
                ))
                for app in apps:
                    app.status = "INTERVIEW"
                    app.save()

                # Robust recruiter resolution: request user → company owner → any staff user
                recruiter_user = None

                # 1. Try the authenticated user who triggered the agent
                if r_user_id:
                    try:
                        recruiter_user = User.objects.get(id=r_user_id)
                    except User.DoesNotExist:
                        pass

                # 2. Try the job's company owner
                if not recruiter_user and apps:
                    try:
                        recruiter_user = apps[0].job.company.owner
                    except Exception:
                        pass

                # 3. Fallback to any staff/superuser
                if not recruiter_user:
                    recruiter_user = User.objects.filter(is_staff=True).first()

                # 4. Last resort: use the first applicant if nothing else works
                if not recruiter_user and apps:
                    recruiter_user = apps[0].applicant

                # Create a formal report for the UI Panel to display
                all_scored = (
                    JobApplication.objects.filter(job_id=j_id, ai_score__isnull=False)
                    .select_related("applicant")
                    .order_by("-ai_score")
                )

                results_data = []
                for rank, cand in enumerate(all_scored[:10], 1):
                    # ai_analysis is stored as a JSON string in the DB by AIService
                    import json
                    try:
                        analysis_dict = json.loads(cand.ai_analysis) if isinstance(cand.ai_analysis, str) else cand.ai_analysis
                    except Exception:
                        analysis_dict = {}

                    # Extract the rich recruiter_view data from AI analysis
                    recruiter_view = analysis_dict.get('recruiter_view', {})
                    intelligence = analysis_dict.get('intelligence', {})

                    # Build a meaningful summary from actual AI analysis
                    explanation = recruiter_view.get('explanation', '')
                    strengths = recruiter_view.get('strengths', [])
                    recommended_action = recruiter_view.get('recommended_action', '')
                    startup_fit = recruiter_view.get('startup_fit', '')
                    primary_role = intelligence.get('summary', {}).get('primary_role', '')
                    years_exp = intelligence.get('summary', {}).get('years_of_experience', 0)

                    # Compose a rich summary from available data
                    if explanation:
                        summary = explanation
                    elif strengths:
                        summary = f"{primary_role} with {years_exp}+ years experience. Key strengths: {', '.join(strengths[:3])}"
                    elif primary_role:
                        summary = f"{primary_role} — {recommended_action}" if recommended_action else f"{primary_role} with {years_exp}+ years experience"
                    else:
                        summary = recommended_action or 'AI screening completed'

                    results_data.append(
                        {
                            "id": str(cand.id),
                            "rank": rank,
                            "name": f"{cand.applicant.first_name} {cand.applicant.last_name}",
                            "email": cand.applicant.email,
                            "score": cand.ai_score,
                            "summary": summary,
                            "analysis": analysis_dict,
                        }
                    )

                if apps:
                    job_title = apps[0].job.title
                else:
                    try:
                        job_title = JobPost.objects.get(id=j_id).title
                    except Exception:
                        job_title = "Unknown Job"

                AIScreeningReport.objects.create(
                    job_id=j_id,
                    job_title=job_title,
                    recruiter=recruiter_user,
                    results={
                        "status": "completed",
                        "job_id": str(j_id),
                        "processed_count": all_scored.count(),
                        "total_applicants": all_scored.count(),
                        "top_candidates": results_data,
                    },
                )
                return True

            await sync_to_async(final_actions, thread_sensitive=False)(
                [app.id for app in top_apps], job_id, recruiter_user_id
            )

            self.log(
                "Autonomous Workflow Completed! View results in the 'AI Screening' panel.",
                action="workflow_complete",
            )
            return True

        except Exception as e:
            self.log(
                f"Autonomous workflow failed: {str(e)}",
                level="ERROR",
                action="workflow_error",
            )
            raise e
        finally:
            # No browser to close in this mode!
            pass

    async def handover_workflow(self, job_data):
        """
        Special workflow that connects to an ALREADY OPEN browser
        and assumes the user is already logged in and looking at the site.
        """
        self.log("Starting Handover Workflow (Connecting to your browser)...")
        return await self.create_job_workflow(job_data, use_existing=True)
