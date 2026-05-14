from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from AIrounds.models import InterviewRound, InterviewQuestion, InterviewSession
from AIrounds.services.engine_service import InterviewEngineService
from AIrounds.services.orchestrator import InterviewOrchestrator
from AIrounds.services.notifier import InterviewNotifier
from AIrounds.views.base import ResponseMixin

class ConfigureInterviewView(APIView, ResponseMixin):
    """
    Step 3/4: Recruiter configures the rounds and AI orchestrates the session.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        application_id = request.data.get('job_application_id') or request.data.get('application_id')
        overall_config = request.data.get('overall_config', {})
        rounds_config = request.data.get('rounds') or request.data.get('rounds_config', [])

        if not application_id or not rounds_config:
            return self.build_response("error", "application_id and rounds_config are required.", {}, status.HTTP_400_BAD_REQUEST)

        try:
            session, rounds = InterviewOrchestrator.create_interview_from_config(
                application_id, overall_config, rounds_config
            )
            
            # Step 5: Send Invitation
            InterviewNotifier.notify_candidate_of_invite(session)

            # Step 6: Auto-generate candidate exam link
            from AIrounds.models import CandidateInterviewLink
            from datetime import timedelta
            from django.utils import timezone

            link, _ = CandidateInterviewLink.objects.get_or_create(
                session=session,
                defaults={'expires_at': timezone.now() + timedelta(hours=72)}
            )

            from django.conf import settings as django_settings
            frontend_url = getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000')
            exam_url = f"{frontend_url}/interview/exam"
            
            return self.build_response("success", "Interview orchestrated and invite sent.", {
                "session_id": str(session.id),
                "invite_token": str(session.invite_token),
                "rounds_count": len(rounds),
                "exam_url": exam_url,
                "exam_token": str(link.token),
                "exam_credentials": {
                    "username": link.exam_username,
                    "password": link.exam_password,
                },
            })
        except Exception as e:
            return self.build_response("error", str(e), {}, status.HTTP_500_INTERNAL_SERVER_ERROR)

class GenerateQuestionPoolView(APIView, ResponseMixin):
    """
    Recruiter requests AI to generate a pool of questions for configuration.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        application_id = request.data.get('application_id')
        round_type = request.data.get('type', 'TECHNICAL')
        designation = request.data.get('designation', 'TECHNICAL_SCREENING')
        difficulty = request.data.get('difficulty', 'MID')
        round_category = request.data.get('round_category', 'NON_CODING')
        question_format = request.data.get('question_format', 'TEXT')
        programming_language = request.data.get('programming_language', '')
        count = request.data.get('count', 5)

        if not application_id:
            return self.build_response("error", "application_id is required.", {}, status.HTTP_400_BAD_REQUEST)

        try:
            questions = InterviewEngineService.generate_question_pool(
                application_id, round_type, designation, difficulty, round_category, question_format, programming_language, count
            )
            return self.build_response("success", "Questions generated.", {"questions": questions})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self.build_response("error", str(e), {}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class RecruiterSessionListView(APIView, ResponseMixin):
    """
    Returns a list of all interview sessions orchestrated by the recruiter's company.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        from startups.models import CompanyProfile
        from jobs.models import JobApplication
        try:
            company = CompanyProfile.objects.get(owner=request.user)
            
            # 1. Get all InterviewSessions for the company that are in the INTERVIEW stage
            all_sessions = InterviewSession.objects.filter(
                application__job__company=company,
                application__job__status='ACTIVE',
                application__status='INTERVIEW'
            ).select_related('candidate', 'application', 'application__job').prefetch_related('rounds').order_by('-created_at')
            
            data = []
            seen_application_ids = set()
            
            # Add unique latest sessions
            for s in all_sessions:
                app_id = str(s.application.id) if s.application else None
                
                # Deduplicate: Only take the latest session for each application
                if app_id:
                    if app_id in seen_application_ids:
                        continue
                    seen_application_ids.add(app_id)
                
                # Get exam link credentials if available
                exam_creds = None
                exam_link_url = None
                try:
                    active_link = s.active_link
                    exam_creds = {
                        "username": active_link.exam_username,
                        "password": active_link.exam_password,
                    }
                    exam_link_url = f"/interview/exam"
                except Exception:
                    pass

                data.append({
                    "id": str(s.id),
                    "candidate_name": f"{s.candidate.first_name} {s.candidate.last_name}",
                    "job_title": s.job_title,
                    "job_id": str(s.application.job.id) if s.application and s.application.job else None,
                    "status": s.status,
                    "overall_score": s.overall_score,
                    "created_at": s.created_at,
                    "rounds_count": s.rounds.count(),
                    "application_id": app_id,
                    "is_orchestrated": True,
                    "exam_credentials": exam_creds,
                    "exam_link_url": exam_link_url,
                })

            # 2. Get JobApplications with status='INTERVIEW' that don't have a session yet
            pending_apps = JobApplication.objects.filter(
                job__company=company,
                job__status='ACTIVE',
                status='INTERVIEW'
            ).exclude(
                id__in=seen_application_ids
            ).select_related('applicant', 'job')

            # Add pending orchestrations
            for app in pending_apps:
                data.append({
                    "id": f"pending_{app.id}",
                    "candidate_name": f"{app.applicant.first_name} {app.applicant.last_name}",
                    "job_title": app.job.title,
                    "job_id": str(app.job.id),
                    "status": "READY_TO_ORCHESTRATE",
                    "overall_score": None,
                    "created_at": app.updated_at,
                    "rounds_count": 0,
                    "application_id": str(app.id),
                    "is_orchestrated": False
                })

            # Sort by created_at descending
            data.sort(key=lambda x: x['created_at'], reverse=True)
            
            return self.build_response("success", "Interview pipeline data retrieved.", data)
        except CompanyProfile.DoesNotExist:
            return self.build_response("error", "Company profile not found.", {}, status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return self.build_response("error", str(e), {}, status.HTTP_500_INTERNAL_SERVER_ERROR)



class GenerateInterviewLinkView(APIView, ResponseMixin):
    """
    Recruiter generates an active exam link for a candidate's interview session.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        from AIrounds.models import CandidateInterviewLink
        from datetime import timedelta
        from django.utils import timezone
        from django.conf import settings as django_settings

        session_id = request.data.get('session_id')
        expiry_hours = request.data.get('expiry_hours', 72)  # Default 3 days

        if not session_id:
            return self.build_response("error", "session_id is required.", {}, status.HTTP_400_BAD_REQUEST)

        try:
            session = InterviewSession.objects.get(id=session_id)
        except InterviewSession.DoesNotExist:
            return self.build_response("error", "Session not found.", {}, status.HTTP_404_NOT_FOUND)

        # Check if link already exists
        existing_link = CandidateInterviewLink.objects.filter(session=session).first()
        frontend_url = getattr(django_settings, 'FRONTEND_URL', 'http://localhost:3000')
        exam_url = f"{frontend_url}/interview/exam"

        if existing_link:
            return self.build_response("success", "Interview link already exists.", {
                "link_id": str(existing_link.id),
                "token": str(existing_link.token),
                "exam_url": exam_url,
                "status": existing_link.status,
                "expires_at": existing_link.expires_at.isoformat() if existing_link.expires_at else None,
                "is_valid": existing_link.is_valid,
                "exam_credentials": {
                    "username": existing_link.exam_username,
                    "password": existing_link.exam_password,
                },
            })

        # Create new link
        link = CandidateInterviewLink.objects.create(
            session=session,
            expires_at=timezone.now() + timedelta(hours=expiry_hours),
        )

        return self.build_response("success", "Interview link generated.", {
            "link_id": str(link.id),
            "token": str(link.token),
            "exam_url": exam_url,
            "status": link.status,
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
            "exam_credentials": {
                "username": link.exam_username,
                "password": link.exam_password,
            },
        }, status.HTTP_201_CREATED)



class SessionDetailView(APIView, ResponseMixin):
    """
    Returns full session detail with all rounds, questions, and exam link info.
    Used by the recruiter pipeline for the edit/detail panel.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, session_id):
        try:
            session = InterviewSession.objects.select_related(
                'candidate', 'application__job'
            ).prefetch_related('rounds__questions').get(id=session_id)
        except InterviewSession.DoesNotExist:
            return self.build_response("error", "Session not found.", {}, status.HTTP_404_NOT_FOUND)

        # Build rounds and questions
        rounds_data = []
        for rnd in session.rounds.all().order_by('created_at'):
            questions = []
            for q in rnd.questions.all().order_by('asked_at'):
                questions.append({
                    "id": str(q.id),
                    "question_text": q.question_text,
                    "ideal_answer": q.ideal_answer,
                    "question_type": q.question_type,
                    "mcq_options": q.mcq_options,
                    "candidate_answer": q.candidate_answer,
                    "answered_at": q.answered_at.isoformat() if q.answered_at else None,
                    "evaluation": q.evaluation,
                })
            rounds_data.append({
                "id": str(rnd.id),
                "designation": rnd.designation,
                "designation_display": rnd.get_designation_display(),
                "strategy_tier": rnd.strategy_tier,
                "round_category": rnd.round_category,
                "difficulty": rnd.difficulty,
                "question_format": rnd.question_format,
                "programming_language": rnd.programming_language,
                "timer_seconds": rnd.timer_seconds,
                "max_questions": rnd.max_questions,
                "status": rnd.status,
                "questions": questions,
            })

        # Exam link info
        exam_info = None
        try:
            link = session.active_link
            exam_info = {
                "token": str(link.token),
                "exam_username": link.exam_username,
                "exam_password": link.exam_password,
                "status": link.status,
                "expires_at": link.expires_at.isoformat() if link.expires_at else None,
                "started_at": link.started_at.isoformat() if link.started_at else None,
                "completed_at": link.completed_at.isoformat() if link.completed_at else None,
                "is_valid": link.is_valid,
            }
        except Exception:
            pass

        return self.build_response("success", "Session details retrieved.", {
            "id": str(session.id),
            "candidate_name": f"{session.candidate.first_name} {session.candidate.last_name}",
            "candidate_email": session.candidate.email,
            "job_title": session.job_title,
            "status": session.status,
            "overall_score": session.overall_score,
            "created_at": session.created_at.isoformat(),
            "rounds": rounds_data,
            "exam_link": exam_info,
        })



class DeleteQuestionView(APIView, ResponseMixin):
    """
    Recruiter deletes a specific question from a round.
    """
    permission_classes = (IsAuthenticated,)

    def delete(self, request, question_id):
        try:
            question = InterviewQuestion.objects.get(id=question_id)
        except InterviewQuestion.DoesNotExist:
            return self.build_response("error", "Question not found.", {}, status.HTTP_404_NOT_FOUND)

        round_id = str(question.round.id)
        question.delete()

        return self.build_response("success", "Question deleted.", {
            "round_id": round_id,
            "deleted_question_id": str(question_id),
        })



class RegenerateRoundQuestionsView(APIView, ResponseMixin):
    """
    Recruiter regenerates AI questions for a specific round.
    Clears existing questions and generates new ones.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request, round_id):
        try:
            rnd = InterviewRound.objects.select_related('session__application').get(id=round_id)
        except InterviewRound.DoesNotExist:
            return self.build_response("error", "Round not found.", {}, status.HTTP_404_NOT_FOUND)

        count = request.data.get('count', rnd.max_questions or 5)

        try:
            # Get application_id from the round's session
            application_id = str(rnd.session.application.id)

            # Generate new questions
            questions = InterviewEngineService.generate_question_pool(
                application_id,
                rnd.round_type or rnd.designation,
                rnd.designation,
                rnd.difficulty,
                rnd.question_format,
                rnd.programming_language,
                count
            )

            # Delete old questions
            rnd.questions.all().delete()

            # Create new questions
            new_questions = []
            for q_data in questions:
                # Handle both string (fallback) and dict (new format)
                if isinstance(q_data, dict):
                    q_text = q_data.get('question')
                    q_ideal = q_data.get('ideal_answer')
                else:
                    q_text = q_data
                    q_ideal = None

                q = InterviewQuestion.objects.create(
                    round=rnd,
                    question_text=q_text,
                    ideal_answer=q_ideal,
                    question_type=rnd.question_format or 'TEXT',
                )
                new_questions.append({
                    "id": str(q.id),
                    "question_text": q.question_text,
                    "ideal_answer": q.ideal_answer,
                    "question_type": q.question_type,
                })

            return self.build_response("success", f"{len(new_questions)} questions regenerated.", {
                "round_id": str(rnd.id),
                "questions": new_questions,
            })
        except Exception as e:
            return self.build_response("error", str(e), {}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class EvaluateSessionView(APIView, ResponseMixin):
    """
    Aggregates scores for all rounds in a session.
    Does NOT call AI — only recalculates from existing evaluations.
    For AI evaluation, use EvaluateQuestionView per question.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request, session_id):
        try:
            session = InterviewSession.objects.prefetch_related('rounds__questions').get(id=session_id)
        except InterviewSession.DoesNotExist:
            return self.build_response("error", "Session not found.", {}, status.HTTP_404_NOT_FOUND)

        results = []
        total_session_score = 0
        total_max_marks = 0
        unevaluated_count = 0

        for rnd in session.rounds.all():
            round_score = 0
            for q in rnd.questions.all():
                if q.evaluation and isinstance(q.evaluation, dict):
                    score = q.evaluation.get('score', 0)
                    round_score += score
                    total_session_score += score
                elif q.candidate_answer:
                    unevaluated_count += 1

                total_max_marks += q.marks

            rnd.round_score = round_score
            rnd.save()
            results.append({
                "round_id": str(rnd.id),
                "round_score": round_score,
            })

        session.overall_score = total_session_score
        if unevaluated_count == 0 and total_max_marks > 0:
            session.status = 'COMPLETED'
        session.save()

        return self.build_response("success", "Score aggregation complete.", {
            "session_id": str(session.id),
            "overall_score": total_session_score,
            "total_max_marks": total_max_marks,
            "unevaluated_count": unevaluated_count,
            "rounds": results
        })


class EvaluateQuestionView(APIView, ResponseMixin):
    """
    Evaluates a SINGLE question using AI.
    Called per-question from the frontend for real-time progress.
    Fast enough to avoid ASGI timeout (single Gemini call ~3-5s).
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request, question_id):
        try:
            question = InterviewQuestion.objects.select_related(
                'round__session'
            ).get(id=question_id)
        except InterviewQuestion.DoesNotExist:
            return self.build_response("error", "Question not found.", {}, status.HTTP_404_NOT_FOUND)

        if not question.candidate_answer:
            return self.build_response("error", "No candidate answer to evaluate.", {}, status.HTTP_400_BAD_REQUEST)

        # Skip if already evaluated (unless force=true)
        force = request.data.get('force', False)
        if question.evaluation and not force:
            return self.build_response("success", "Already evaluated.", {
                "question_id": str(question.id),
                "evaluation": question.evaluation,
                "already_evaluated": True,
            })

        try:
            eval_data = InterviewEngineService.evaluate_answer(
                str(question.round.session.id),
                str(question.round.id),
                str(question.id),
                question.candidate_answer
            )
            return self.build_response("success", "Question evaluated.", {
                "question_id": str(question.id),
                "evaluation": eval_data,
                "already_evaluated": False,
            })
        except Exception as e:
            import logging
            logger = logging.getLogger("ai_rounds.recruiter")
            logger.error(f"Error evaluating question {question_id}: {e}")
            return self.build_response("error", str(e), {}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeleteInterviewSessionView(APIView, ResponseMixin):
    """
    Deletes an interview session permanently.
    """
    permission_classes = (IsAuthenticated,)

    def delete(self, request, session_id):
        from jobs.models import JobApplication
        try:
            if session_id.startswith('pending_'):
                # Handle pending (non-orchestrated) candidates:
                # DON'T delete the application — just revert status back to REVIEWED
                # so it leaves the pipeline but the application data is preserved.
                application_id = session_id.replace('pending_', '')
                try:
                    application = JobApplication.objects.select_related('job__company').get(id=application_id)
                    
                    # Verify ownership
                    from startups.models import CompanyProfile
                    company = CompanyProfile.objects.get(owner=request.user)
                    if application.job.company != company:
                        return self.build_response("error", "Unauthorized.", {}, status.HTTP_403_FORBIDDEN)
                    
                    # Revert status instead of deleting the whole application
                    application.status = 'REVIEWED'
                    application.save()
                    return self.build_response("success", "Candidate removed from interview pipeline.", {})
                except JobApplication.DoesNotExist:
                    return self.build_response("error", "Application not found.", {}, status.HTTP_404_NOT_FOUND)
            
            # Handle orchestrated session deletion:
            # ONLY delete the InterviewSession (rounds, questions, exam link cascade automatically).
            # The JobApplication and JobPost remain intact.
            session = InterviewSession.objects.select_related('application__job__company').get(id=session_id)
            
            # Verify ownership
            from startups.models import CompanyProfile
            try:
                company = CompanyProfile.objects.get(owner=request.user)
                if session.application and session.application.job.company != company:
                    return self.build_response("error", "Unauthorized.", {}, status.HTTP_403_FORBIDDEN)
            except CompanyProfile.DoesNotExist:
                return self.build_response("error", "Company profile not found.", {}, status.HTTP_404_NOT_FOUND)
            
            # Only delete the interview session — NOT the application
            # Django CASCADE will automatically delete: rounds → questions, exam links
            session.delete()
            return self.build_response("success", "Interview session deleted. Application data preserved.", {})
        except InterviewSession.DoesNotExist:
            return self.build_response("error", "Session not found.", {}, status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return self.build_response("error", str(e), {}, status.HTTP_500_INTERNAL_SERVER_ERROR)
