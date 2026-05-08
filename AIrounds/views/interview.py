from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from AIrounds.models import InterviewRound, InterviewQuestion, InterviewSession
from AIrounds.services.engine_service import InterviewEngineService
from AIrounds.services.state_service import InterviewStateService
from AIrounds.services.orchestrator import InterviewOrchestrator
from AIrounds.services.reporter import InterviewReporter
from AIrounds.views.base import ResponseMixin

class VerifyInviteTokenView(APIView, ResponseMixin):
    """
    Step 6/7: Candidate verifies the invite token before starting.
    """
    def get(self, request, token):
        session, error = InterviewOrchestrator.get_session_by_token(token)
        if error:
            return self.build_response("error", error, {}, status.HTTP_403_FORBIDDEN)
            
        return self.build_response("success", "Token verified.", {
            "session_id": str(session.id),
            "job_title": session.job_title,
            "candidate_name": f"{session.candidate.first_name} {session.candidate.last_name}",
            "status": session.status,
            "verification_status": session.verification_status
        })


class StartInterviewView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        """
        Step 8: Starts/Activates the interview session. 
        Can be called directly or via token.
        """
        token = request.data.get('token')
        if token:
            session, error = InterviewOrchestrator.get_session_by_token(token)
            if error:
                return self.build_response("error", error, {}, status.HTTP_403_FORBIDDEN)
            
            # Activate session if pending
            if session.status == 'PENDING':
                session.status = 'ACTIVE'
                session.save()
                
            first_round = session.rounds.filter(status='PENDING').order_by('created_at').first()
            if first_round:
                first_round.status = 'ACTIVE'
                first_round.save()

            return self.build_response("success", "Interview session activated.", {
                "session_id": str(session.id),
                "round_id": str(first_round.id) if first_round else None,
                "round_type": first_round.round_type if first_round else None
            })

        # Legacy manual start logic (internal/testing)
        job_title = request.data.get('job_title')
        job_description = request.data.get('job_description')
        round_type = request.data.get('round_type', 'TECHNICAL_ROUND')
        difficulty = request.data.get('difficulty', 'MEDIUM')
        
        if not job_title or not job_description:
            return self.build_response("error", "job_title and job_description are required.", {}, status.HTTP_400_BAD_REQUEST)

        try:
            session = InterviewStateService.start_session(
                request.user, job_title, job_description
            )
            round_obj = InterviewStateService.add_round(session.id, round_type, difficulty)
            
            return self.build_response("success", "Manual interview session started.", {
                "session_id": str(session.id),
                "round_id": str(round_obj.id),
                "round_type": round_obj.round_type
            })
        except Exception as e:
            return self.build_response("error", str(e), {}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetNextQuestionView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, round_id):
        """Generates the next question for a given round."""
        try:
            round_obj = InterviewRound.objects.get(id=round_id)
            session_id = round_obj.session.id
            
            question_data = InterviewEngineService.generate_next_question(session_id, round_id)
            return self.build_response("success", "Question generated.", question_data)
        except InterviewRound.DoesNotExist:
            return self.build_response("error", "Round not found.", {}, status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return self.build_response("error", str(e), {}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class SubmitAnswerView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, question_id):
        """Submits an answer and gets evaluation."""
        answer_text = request.data.get('answer')
        if not answer_text:
            return self.build_response("error", "answer is required.", {}, status.HTTP_400_BAD_REQUEST)

        try:
            question = InterviewQuestion.objects.get(id=question_id)
            round_obj = question.round
            session_id = round_obj.session.id
            
            evaluation = InterviewEngineService.evaluate_answer(
                session_id, round_obj.id, question_id, answer_text
            )
            return self.build_response("success", "Answer evaluated.", evaluation)
        except InterviewQuestion.DoesNotExist:
            return self.build_response("error", "Question not found.", {}, status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return self.build_response("error", str(e), {}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetRoundSummaryView(APIView, ResponseMixin):
    permission_classes = (IsAuthenticated,)

    def post(self, request, round_id):
        """Completes the round and returns a final summary."""
        try:
            round_obj = InterviewRound.objects.get(id=round_id)
            session_id = round_obj.session.id
            
            summary = InterviewEngineService.generate_round_summary(session_id, round_id)
            return self.build_response("success", "Round summary generated.", summary)
        except InterviewRound.DoesNotExist:
            return self.build_response("error", "Round not found.", {}, status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return self.build_response("error", str(e), {}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class UpdateVerificationView(APIView, ResponseMixin):
    """
    Step 7: Candidate updates their identity/device verification status.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request, session_id):
        verification_data = request.data.get('verification_data')
        if not verification_data:
            return self.build_response("error", "verification_data is required.", {}, status.HTTP_400_BAD_REQUEST)

        try:
            session = InterviewSession.objects.get(id=session_id, candidate=request.user)
            # Merge existing verification status with new data
            session.verification_status.update(verification_data)
            session.save()
            
            return self.build_response("success", "Verification status updated.", session.verification_status)
        except InterviewSession.DoesNotExist:
            return self.build_response("error", "Session not found.", {}, status.HTTP_404_NOT_FOUND)


class GenerateFinalReportView(APIView, ResponseMixin):
    """
    Step 11: Final synthesis of all rounds into a hiring report.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request, session_id):
        try:
            report = InterviewReporter.generate_final_report(session_id)
            return self.build_response("success", "Final interview report generated.", report)
        except Exception as e:
            return self.build_response("error", str(e), {}, status.HTTP_500_INTERNAL_SERVER_ERROR)

