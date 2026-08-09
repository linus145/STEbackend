from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from AIrounds.models import InterviewQuestion, InterviewSession
from AIrounds.views.base import ResponseMixin
import logging

logger = logging.getLogger(__name__)

class CandidateExamAccessView(APIView, ResponseMixin):
    """
    Candidate accesses their exam via the active link token.
    No authentication required — the token IS the authentication.
    """
    permission_classes = (AllowAny,)
    authentication_classes = []

    def get(self, request, token):
        from AIrounds.models import CandidateInterviewLink

        try:
            link = CandidateInterviewLink.objects.select_related(
                'session', 'session__candidate'
            ).get(token=token)
        except CandidateInterviewLink.DoesNotExist:
            return self.build_response("error", "Invalid exam link.", {}, status.HTTP_404_NOT_FOUND)

        if not link.is_valid:
            return self.build_response("error", "This exam link has expired or already been completed.", {}, status.HTTP_403_FORBIDDEN)

        session = link.session

        # Build rounds + questions payload
        rounds_data = []
        for rnd in session.rounds.all().order_by('created_at'):
            if rnd.question_format == 'VIDEO' and rnd.questions.count() == 0:
                try:
                    from AIrounds.services.engine_service import InterviewEngineService
                    InterviewEngineService.generate_next_question(str(session.id), str(rnd.id))
                except Exception as e:
                    logger.error(f"Error generating dynamic first question: {e}")
            elif rnd.question_format == 'ONLINE_INTERVIEW' and rnd.questions.count() == 0:
                try:
                    from AIrounds.services.engine_service import InterviewEngineService
                    application_id = str(session.application.id) if session.application else None
                    if application_id:
                        coding_topics = rnd.settings.get('coding_topics') if isinstance(rnd.settings, dict) else None
                        coding_frameworks = rnd.settings.get('coding_frameworks') if isinstance(rnd.settings, dict) else None
                        count = rnd.max_questions or 5
                        
                        questions = InterviewEngineService.generate_question_pool(
                            application_id=application_id,
                            round_type=rnd.round_type or rnd.designation,
                            designation=rnd.designation,
                            difficulty=rnd.difficulty,
                            round_category=rnd.round_category or 'NON_CODING',
                            question_format='TEXT',
                            programming_language=rnd.programming_language or '',
                            count=count,
                            coding_topics=coding_topics,
                            coding_frameworks=coding_frameworks
                        )
                        
                        for q_idx, q_data in enumerate(questions):
                            if isinstance(q_data, dict):
                                q_text = q_data.get('question')
                                q_ideal = q_data.get('ideal_answer')
                            else:
                                q_text = q_data
                                q_ideal = None
                                
                            InterviewQuestion.objects.create(
                                round=rnd,
                                question_text=q_text,
                                ideal_answer=q_ideal,
                                question_type='ONLINE_INTERVIEW',
                                marks=10
                            )
                    else:
                        InterviewQuestion.objects.create(
                            round=rnd,
                            question_text="Face-to-Face Online Interview in progress. Recruiter will ask questions live.",
                            question_type="ONLINE_INTERVIEW",
                            marks=10
                        )
                except Exception as e:
                    logger.error(f"Error creating online interview questions: {e}")
                    if rnd.questions.count() == 0:
                        InterviewQuestion.objects.create(
                            round=rnd,
                            question_text="Face-to-Face Online Interview in progress. Recruiter will ask questions live.",
                            question_type="ONLINE_INTERVIEW",
                            marks=10
                        )

            questions = []
            for q in rnd.questions.all().order_by('asked_at'):
                q_data = {
                    "id": str(q.id),
                    "question_text": q.question_text,
                    "question_type": q.question_type,
                    "mcq_options": q.mcq_options,
                }
                questions.append(q_data)

            rounds_data.append({
                "id": str(rnd.id),
                "designation": rnd.designation,
                "strategy_tier": rnd.strategy_tier,
                "difficulty": rnd.difficulty,
                "question_format": rnd.question_format,
                "programming_language": rnd.programming_language,
                "timer_seconds": rnd.timer_seconds,
                "max_questions": rnd.max_questions,
                "questions": questions,
            })

        # Include voice agent API keys only when a VIDEO round exists
        voice_agent_keys = {}
        if any(rnd.question_format == 'VIDEO' for rnd in session.rounds.all()):
            from django.conf import settings as dj_settings
            voice_agent_keys = {
                "deepgram_api_key": dj_settings.DEEPGRAM_API_KEY,
                "gemini_api_key": dj_settings.GEMINI_API_KEY,
            }

        return self.build_response("success", "Exam data loaded.", {
            "session_id": str(session.id),
            "job_title": session.job_title,
            "candidate_name": f"{session.candidate.first_name} {session.candidate.last_name}",
            "status": link.status,
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
            "rounds": rounds_data,
            **voice_agent_keys,
        })

    def post(self, request, token):
        """Candidate starts the exam — marks the link as STARTED."""
        from AIrounds.models import CandidateInterviewLink
        from django.utils import timezone

        try:
            link = CandidateInterviewLink.objects.get(token=token)
        except CandidateInterviewLink.DoesNotExist:
            return self.build_response("error", "Invalid exam link.", {}, status.HTTP_404_NOT_FOUND)

        if not link.is_valid:
            return self.build_response("error", "This exam link has expired or already been completed.", {}, status.HTTP_403_FORBIDDEN)

        link.status = 'STARTED'
        link.started_at = timezone.now()
        link.ip_address = request.META.get('REMOTE_ADDR')
        link.user_agent = request.META.get('HTTP_USER_AGENT', '')
        link.save()

        # Also activate the session
        link.session.status = 'ACTIVE'
        link.session.save(update_fields=['status'])

        return self.build_response("success", "Exam started.", {
            "session_id": str(link.session.id),
            "started_at": link.started_at.isoformat(),
        })



from maincore.throttling import LoginBurstThrottle, LoginSustainedThrottle

class CandidateExamLoginView(APIView, ResponseMixin):
    """
    Candidate logs in with exam credentials (NOT Django auth).
    Returns the full exam data if credentials are valid.
    """
    permission_classes = (AllowAny,)
    authentication_classes = []
    throttle_classes = [LoginBurstThrottle, LoginSustainedThrottle]

    def post(self, request):
        from AIrounds.models import CandidateInterviewLink

        username = request.data.get('username', '').strip()
        password = request.data.get('password', '').strip()

        if not username or not password:
            return self.build_response("error", "Username and password are required.", {}, status.HTTP_400_BAD_REQUEST)

        try:
            link = CandidateInterviewLink.objects.select_related(
                'session', 'session__candidate'
            ).get(exam_username=username)
        except CandidateInterviewLink.DoesNotExist:
            return self.build_response("error", "Invalid credentials.", {}, status.HTTP_401_UNAUTHORIZED)

        if link.exam_password != password:
            return self.build_response("error", "Invalid credentials.", {}, status.HTTP_401_UNAUTHORIZED)

        if not link.is_valid:
            return self.build_response("error", "This exam has expired or already been completed.", {}, status.HTTP_403_FORBIDDEN)

        session = link.session

        # Start the exam session on login
        from django.utils import timezone
        if link.status == 'ACTIVE':
            link.status = 'STARTED'
            link.started_at = timezone.now()
            link.ip_address = request.META.get('REMOTE_ADDR')
            link.user_agent = request.META.get('HTTP_USER_AGENT', '')
            link.save(update_fields=['status', 'started_at', 'ip_address', 'user_agent'])

            session.status = 'ACTIVE'
            session.save(update_fields=['status'])

        # Build full exam payload
        rounds_data = []
        for rnd in session.rounds.all().order_by('created_at'):
            if rnd.question_format == 'VIDEO' and rnd.questions.count() == 0:
                try:
                    from AIrounds.services.engine_service import InterviewEngineService
                    InterviewEngineService.generate_next_question(str(session.id), str(rnd.id))
                except Exception as e:
                    logger.error(f"Error generating dynamic first question: {e}")
            elif rnd.question_format == 'ONLINE_INTERVIEW' and rnd.questions.count() == 0:
                try:
                    from AIrounds.services.engine_service import InterviewEngineService
                    application_id = str(session.application.id) if session.application else None
                    if application_id:
                        coding_topics = rnd.settings.get('coding_topics') if isinstance(rnd.settings, dict) else None
                        coding_frameworks = rnd.settings.get('coding_frameworks') if isinstance(rnd.settings, dict) else None
                        count = rnd.max_questions or 5
                        
                        questions = InterviewEngineService.generate_question_pool(
                            application_id=application_id,
                            round_type=rnd.round_type or rnd.designation,
                            designation=rnd.designation,
                            difficulty=rnd.difficulty,
                            round_category=rnd.round_category or 'NON_CODING',
                            question_format='TEXT',
                            programming_language=rnd.programming_language or '',
                            count=count,
                            coding_topics=coding_topics,
                            coding_frameworks=coding_frameworks
                        )
                        
                        for q_idx, q_data in enumerate(questions):
                            if isinstance(q_data, dict):
                                q_text = q_data.get('question')
                                q_ideal = q_data.get('ideal_answer')
                            else:
                                q_text = q_data
                                q_ideal = None
                                
                            InterviewQuestion.objects.create(
                                round=rnd,
                                question_text=q_text,
                                ideal_answer=q_ideal,
                                question_type='ONLINE_INTERVIEW',
                                marks=10
                            )
                    else:
                        InterviewQuestion.objects.create(
                            round=rnd,
                            question_text="Face-to-Face Online Interview in progress. Recruiter will ask questions live.",
                            question_type="ONLINE_INTERVIEW",
                            marks=10
                        )
                except Exception as e:
                    logger.error(f"Error creating online interview questions: {e}")
                    if rnd.questions.count() == 0:
                        InterviewQuestion.objects.create(
                            round=rnd,
                            question_text="Face-to-Face Online Interview in progress. Recruiter will ask questions live.",
                            question_type="ONLINE_INTERVIEW",
                            marks=10
                        )

            questions = []
            for q in rnd.questions.all().order_by('asked_at'):
                q_data = {
                    "id": str(q.id),
                    "question_text": q.question_text,
                    "question_type": q.question_type,
                    "mcq_options": q.mcq_options,
                    "candidate_answer": q.candidate_answer,
                    "answered_at": q.answered_at.isoformat() if q.answered_at else None,
                }
                questions.append(q_data)

            rounds_data.append({
                "id": str(rnd.id),
                "designation": rnd.designation,
                "designation_display": rnd.get_designation_display(),
                "strategy_tier": rnd.strategy_tier,
                "difficulty": rnd.difficulty,
                "question_format": rnd.question_format,
                "programming_language": rnd.programming_language,
                "timer_seconds": rnd.timer_seconds,
                "max_questions": rnd.max_questions,
                "questions": questions,
            })

        # Include voice agent API keys only when a VIDEO round exists
        voice_agent_keys = {}
        if any(rnd.question_format == 'VIDEO' for rnd in session.rounds.all()):
            from django.conf import settings as dj_settings
            voice_agent_keys = {
                "deepgram_api_key": dj_settings.DEEPGRAM_API_KEY,
                "gemini_api_key": dj_settings.GEMINI_API_KEY,
            }

        return self.build_response("success", "Login successful.", {
            "session_id": str(session.id),
            "exam_token": str(link.token),
            "job_title": session.job_title,
            "candidate_name": f"{session.candidate.first_name} {session.candidate.last_name}",
            "status": link.status,
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
            "rounds": rounds_data,
            **voice_agent_keys,
        })



class CandidateSubmitAnswerView(APIView, ResponseMixin):
    """
    Candidate submits an answer for a specific question.
    Authenticated via exam_token in request body.
    """
    permission_classes = (AllowAny,)
    authentication_classes = []

    def post(self, request, question_id):
        from AIrounds.models import CandidateInterviewLink
        from django.utils import timezone

        exam_token = request.data.get('exam_token')
        answer = request.data.get('answer', '')

        if not exam_token:
            return self.build_response("error", "exam_token is required.", {}, status.HTTP_400_BAD_REQUEST)

        try:
            link = CandidateInterviewLink.objects.get(token=exam_token)
        except CandidateInterviewLink.DoesNotExist:
            return self.build_response("error", "Invalid exam token.", {}, status.HTTP_401_UNAUTHORIZED)

        if not link.is_valid:
            return self.build_response("error", "Exam has expired or been completed.", {}, status.HTTP_403_FORBIDDEN)

        # Mark as started if not already
        if link.status == 'ACTIVE':
            link.status = 'STARTED'
            link.started_at = timezone.now()
            link.ip_address = request.META.get('REMOTE_ADDR')
            link.user_agent = request.META.get('HTTP_USER_AGENT', '')
            link.save()
            link.session.status = 'ACTIVE'
            link.session.save(update_fields=['status'])

        # Find and validate the question belongs to this session
        try:
            question = InterviewQuestion.objects.select_related('round__session').get(id=question_id)
        except InterviewQuestion.DoesNotExist:
            return self.build_response("error", "Question not found.", {}, status.HTTP_404_NOT_FOUND)

        if str(question.round.session.id) != str(link.session.id):
            return self.build_response("error", "Unauthorized access.", {}, status.HTTP_403_FORBIDDEN)

        # Save the answer
        question.candidate_answer = answer
        question.answered_at = timezone.now()
        question.save(update_fields=['candidate_answer', 'answered_at'])

        # Generate next follow-up question dynamically if it's a VIDEO round
        next_question_data = None
        if question.round.question_format == 'VIDEO':
            current_q_count = question.round.questions.count()
            if current_q_count < question.round.max_questions:
                try:
                    from AIrounds.services.engine_service import InterviewEngineService
                    InterviewEngineService.generate_next_question(
                        str(link.session.id), 
                        str(question.round.id)
                    )
                    created_q = InterviewQuestion.objects.filter(round=question.round).order_by('-asked_at').first()
                    if created_q and created_q.id != question.id:
                        next_question_data = {
                            "id": str(created_q.id),
                            "question_text": created_q.question_text,
                            "question_type": created_q.question_type,
                            "candidate_answer": "",
                            "answered_at": None,
                        }
                except Exception as e:
                    logger.error(f"Error generating dynamic follow-up question: {e}")

        return self.build_response("success", "Answer submitted.", {
            "question_id": str(question.id),
            "answered_at": question.answered_at.isoformat(),
            "next_question": next_question_data
        })



class CandidateCompleteExamView(APIView, ResponseMixin):
    """
    Candidate finishes the exam. Marks session as completed.
    """
    permission_classes = (AllowAny,)
    authentication_classes = []

    def post(self, request):
        from AIrounds.models import CandidateInterviewLink
        from django.utils import timezone

        exam_token = request.data.get('exam_token')

        if not exam_token:
            return self.build_response("error", "exam_token is required.", {}, status.HTTP_400_BAD_REQUEST)

        try:
            link = CandidateInterviewLink.objects.select_related('session').get(token=exam_token)
        except CandidateInterviewLink.DoesNotExist:
            return self.build_response("error", "Invalid exam token.", {}, status.HTTP_401_UNAUTHORIZED)

        if link.status == 'COMPLETED':
            return self.build_response("error", "Exam already completed.", {}, status.HTTP_400_BAD_REQUEST)

        # Mark link and session as completed
        link.status = 'COMPLETED'
        link.completed_at = timezone.now()
        link.save(update_fields=['status', 'completed_at'])

        link.session.status = 'EVALUATING'
        link.session.save(update_fields=['status'])

        # Count answered questions
        total_questions = 0
        answered_count = 0
        for rnd in link.session.rounds.all():
            for q in rnd.questions.all():
                total_questions += 1
                if q.candidate_answer:
                    answered_count += 1

        return self.build_response("success", "Exam completed successfully.", {
            "session_id": str(link.session.id),
            "completed_at": link.completed_at.isoformat(),
            "total_questions": total_questions,
            "answered_questions": answered_count,
        })


