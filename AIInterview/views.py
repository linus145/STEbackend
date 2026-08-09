from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
import json
from django.conf import settings as dj_settings
from django.utils import timezone
from AIrounds.models import CandidateInterviewLink, InterviewRound, InterviewQuestion
from AIrounds.services.ai_base import AIBaseService
from AIrounds.views.base import ResponseMixin

class AIInterviewSettingsView(APIView, ResponseMixin):
    """
    Serves Deepgram Voice Agent settings and Dynamic LLM Prompt built on the backend.
    """
    permission_classes = (AllowAny,)
    authentication_classes = []

    def get(self, request):
        exam_token = request.query_params.get("exam_token")
        round_id = request.query_params.get("round_id")

        if not exam_token or not round_id:
            return self.build_response(
                "error", 
                "Missing exam_token or round_id query parameters.", 
                {}, 
                status.HTTP_400_BAD_REQUEST
            )

        try:
            link = CandidateInterviewLink.objects.select_related(
                "session", "session__candidate"
            ).get(token=exam_token)
        except CandidateInterviewLink.DoesNotExist:
            return self.build_response(
                "error", 
                "Invalid exam link.", 
                {}, 
                status.HTTP_404_NOT_FOUND
            )

        if not link.is_valid:
            # We can allow STARTED status links to access this endpoint while they are doing the exam.
            if link.status not in ["ACTIVE", "STARTED"]:
                return self.build_response(
                    "error", 
                    "This exam link has expired or already been completed.", 
                    {}, 
                    status.HTTP_403_FORBIDDEN
                )

        session = link.session

        try:
            round_obj = session.rounds.get(id=round_id)
        except InterviewRound.DoesNotExist:
            return self.build_response(
                "error", 
                "Interview round not found for this session.", 
                {}, 
                status.HTTP_404_NOT_FOUND
            )

        # ─── Construct the System Prompt ───
        job_title = session.job_title or "the position"
        candidate_name = f"{session.candidate.first_name} {session.candidate.last_name}" if session.candidate else "Candidate"
        round_designation = round_obj.get_designation_display() or round_obj.designation
        difficulty = round_obj.difficulty or "MID"
        max_questions = round_obj.max_questions or 10
        programming_language = round_obj.programming_language or ""

        prompt = f"""You are Sophia, an elite AI HR Interview Agent conducting a live voice interview for the position of "{job_title}".

INTERVIEW CONTEXT:
- Candidate Name: {candidate_name}
- Round: {round_designation}
- Difficulty Level: {difficulty}
- Maximum Questions: {max_questions}
"""
        if programming_language:
            prompt += f"- Programming Language Focus: {programming_language}\n"

        if session.job_description:
            jd_trimmed = session.job_description[:500] + "..." if len(session.job_description) > 500 else session.job_description
            prompt += f"- Job Description Context: {jd_trimmed}\n"

        if session.candidate_skills:
            prompt += f"- Candidate Skills: {session.candidate_skills}\n"

        prompt += f"""
YOUR BEHAVIOR:
1. You are a warm but professional interviewer. Speak naturally like a real human — use conversational language, brief affirmations ("Great point", "I see", "Interesting").
2. Only introduce yourself briefly in the initial greeting. For all subsequent turns, DO NOT introduce yourself, say 'I am Sophia', or mention you are an AI. Respond or ask the next question directly.
3. Listen carefully to the candidate's answer. Evaluate their response internally for:
   - Technical accuracy and depth
   - Communication clarity
   - Problem-solving approach
   - Relevance to the question
4. After each answer, provide brief acknowledgment, then ask a relevant follow-up question that digs deeper OR move to the next topic.
5. If the candidate's answer is vague or incomplete, probe deeper with clarifying questions like "Can you elaborate on that?" or "What specific approach would you take?"
6. If the candidate's answer demonstrates strong knowledge, challenge them with a harder follow-up.
7. Keep your responses concise — this is a voice conversation, not a lecture. Aim for 2-4 sentences per response.
8. Track the flow naturally. After covering {max_questions} question areas, wrap up the interview professionally.
9. NEVER reveal scores, evaluations, or internal assessment to the candidate.
10. NEVER break character. You are Sophia, the AI interviewer.

ROUND-SPECIFIC FOCUS for "{round_designation}":
- Ask questions directly relevant to this round type.
- For technical rounds: test frameworks, architecture, debugging, scalability.
- For HR rounds: cultural fit, teamwork, leadership, career goals.
- For coding rounds: algorithms, problem-solving methodology, complexity analysis.
- For behavioral rounds: situational questions, conflict resolution, past experience stories.
"""
        if programming_language:
            prompt += f"- For this coding round, prioritize evaluation and questions related to the {programming_language} programming language.\n"

        prompt += "\nBegin the interview now. (If this is the initial greeting, introduce yourself and ask the first question. If you are responding to a message in the chat history, do not introduce yourself again)."

        # ─── Construct Deepgram Settings JSON payload ───
        settings_payload = {
            "type": "Settings",
            "audio": {
                "input": {
                    "encoding": "linear16",
                    "sample_rate": 16000,
                },
                "output": {
                    "encoding": "linear16",
                    "sample_rate": 16000,
                    "container": "none",
                }
            },
            "agent": {
                "listen": {
                    "provider": {
                        "type": "deepgram",
                        "model": "nova-2",
                    },
                },
                "think": {
                    "provider": {
                        "type": "open_ai",
                        "model": "gemini-2.5-flash",
                    },
                    "prompt": prompt,
                },
                "speak": {
                    "provider": {
                        "type": "deepgram",
                        "model": "aura-2-asteria-en",
                    },
                },
                "greeting": f"Hello {candidate_name}! I am Sophia, your AI interviewer today. Let's begin the interview for the {round_designation} round. Could you please introduce yourself and tell me a bit about your background?"
            }
        }

        # Securely configure the custom OpenAI-compatible Google endpoint if key is available
        gemini_key = getattr(dj_settings, "GEMINI_API_KEY", None)
        if gemini_key:
            settings_payload["agent"]["think"]["endpoint"] = {
                "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                "headers": {
                    "Authorization": f"Bearer {gemini_key}",
                    "Content-Type": "application/json"
                }
            }
        else:
            # Fallback if no key is configured on the backend
            settings_payload["agent"]["think"]["provider"]["type"] = "google"
            settings_payload["agent"]["think"]["provider"]["model"] = "gemini-2.5-flash"

        return self.build_response(
            "success", 
            "Deepgram settings generated successfully.", 
            {"settings": settings_payload}
        )


class AIInterviewSubmitView(APIView, ResponseMixin):
    """
    Submits a VIDEO/voice round answer transcript, dynamically splits it using AI,
    and updates/creates individual InterviewQuestion records.
    """
    permission_classes = (AllowAny,)
    authentication_classes = []

    @staticmethod
    def split_voice_transcript(transcript, model_name="gemini-2.5-flash"):
        prompt = (
            "You are an expert data parser. Your task is to analyze the following voice interview transcript between an AI Interviewer (Sophia) and a Candidate, and split it into a list of individual questions asked by the interviewer and the corresponding answers provided by the candidate.\n\n"
            f"TRANSCRIPT:\n{transcript}\n\n"
            "CRITICAL RULES:\n"
            "1. Extract each distinct question asked by the Interviewer.\n"
            "2. Pair it with the Candidate's spoken response immediately following it. If the candidate spoke in multiple segments, combine them into one response.\n"
            "3. Return the output as a valid JSON array of objects, where each object has 'question' (the exact or slightly cleaned text of the question asked) and 'answer' (the combined candidate's response).\n"
            "4. Do not include markdown formatting, json tags, or any wrapper text. Just return the raw JSON array string."
        )
        
        try:
            response_text = AIBaseService.generate_content(
                prompt=prompt,
                system_instruction="You are a precise data parsing assistant. Output strictly valid JSON arrays.",
                temperature=0.1,
                model_name=model_name
            )
            cleaned_text = response_text
            if "```json" in response_text:
                cleaned_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                cleaned_text = response_text.split("```")[1].split("```")[0].strip()
            return json.loads(cleaned_text.strip())
        except Exception as e:
            import logging
            logger = logging.getLogger("ai_interview.submit")
            logger.error(f"Failed to split voice transcript in AIInterview app: {e}")
            return [{"question": "Voice Interview Session", "answer": transcript}]

    def post(self, request, question_id):
        exam_token = request.data.get('exam_token')
        answer = request.data.get('answer', '')

        if not exam_token:
            return self.build_response("error", "exam_token is required.", {}, status.HTTP_400_BAD_REQUEST)

        try:
            link = CandidateInterviewLink.objects.select_related("session", "session__application__job").get(token=exam_token)
        except CandidateInterviewLink.DoesNotExist:
            return self.build_response("error", "Invalid exam token.", {}, status.HTTP_401_UNAUTHORIZED)

        if not link.is_valid:
            return self.build_response("error", "Exam has expired or been completed.", {}, status.HTTP_403_FORBIDDEN)

        # Mark link/session as started if active
        if link.status == 'ACTIVE':
            link.status = 'STARTED'
            link.started_at = timezone.now()
            link.ip_address = request.META.get('REMOTE_ADDR')
            link.user_agent = request.META.get('HTTP_USER_AGENT', '')
            link.save()
            link.session.status = 'ACTIVE'
            link.session.save(update_fields=['status'])

        # Find the question
        try:
            question = InterviewQuestion.objects.select_related('round').get(id=question_id)
        except InterviewQuestion.DoesNotExist:
            return self.build_response("error", "Question not found.", {}, status.HTTP_404_NOT_FOUND)

        if str(question.round.session.id) != str(link.session.id):
            return self.build_response("error", "Unauthorized access.", {}, status.HTTP_403_FORBIDDEN)

        # Resolve model name based on company settings
        company = link.session.application.job.company if (link.session.application and link.session.application.job) else None
        model_name = AIBaseService.get_model_for_company(company)

        # Save and split transcript
        if "Interviewer:" in answer:
            try:
                pairs = self.split_voice_transcript(answer, model_name=model_name)
                if isinstance(pairs, list) and len(pairs) > 0:
                    # 1. Update the first (existing) question
                    first_pair = pairs[0]
                    question.question_text = first_pair.get("question", question.question_text)
                    question.candidate_answer = first_pair.get("answer", "")
                    question.answered_at = timezone.now()
                    question.save(update_fields=['question_text', 'candidate_answer', 'answered_at'])

                    # 2. Clear any other empty questions in this round
                    question.round.questions.exclude(id=question.id).delete()

                    # 3. Create records for the remaining pairs
                    for pair in pairs[1:]:
                        InterviewQuestion.objects.create(
                            round=question.round,
                            question_text=pair.get("question", "Follow-up Question"),
                            candidate_answer=pair.get("answer", ""),
                            question_type="VIDEO",
                            asked_at=timezone.now(),
                            answered_at=timezone.now()
                        )
                else:
                    question.candidate_answer = answer
                    question.answered_at = timezone.now()
                    question.save(update_fields=['candidate_answer', 'answered_at'])
            except Exception as ex:
                import logging
                logger = logging.getLogger("ai_interview.submit")
                logger.error(f"Error processing video submission: {ex}")
                question.candidate_answer = answer
                question.answered_at = timezone.now()
                question.save(update_fields=['candidate_answer', 'answered_at'])
        else:
            # Fallback/Default save
            question.candidate_answer = answer
            question.answered_at = timezone.now()
            question.save(update_fields=['candidate_answer', 'answered_at'])

        return self.build_response("success", "Video round answer split and saved successfully.", {
            "question_id": str(question.id),
            "answered_at": question.answered_at.isoformat() if question.answered_at else timezone.now().isoformat(),
            "next_question": None
        })


class AIInterviewChatView(APIView, ResponseMixin):
    """
    Handles turn-by-turn text-based AI Interview chat backup.
    Constructs the same system prompt and evaluates using Gemini models directly.
    """
    permission_classes = (AllowAny,)
    authentication_classes = []

    def post(self, request):
        exam_token = request.data.get("exam_token")
        round_id = request.data.get("round_id")
        history = request.data.get("history", [])

        if not exam_token or not round_id:
            return self.build_response(
                "error", 
                "Missing exam_token or round_id parameters.", 
                {}, 
                status.HTTP_400_BAD_REQUEST
            )

        try:
            link = CandidateInterviewLink.objects.select_related(
                "session", "session__candidate"
            ).get(token=exam_token)
        except CandidateInterviewLink.DoesNotExist:
            return self.build_response(
                "error", 
                "Invalid exam link.", 
                {}, 
                status.HTTP_404_NOT_FOUND
            )

        session = link.session

        try:
            round_obj = session.rounds.get(id=round_id)
        except InterviewRound.DoesNotExist:
            return self.build_response(
                "error", 
                "Interview round not found for this session.", 
                {}, 
                status.HTTP_404_NOT_FOUND
            )

        # ─── Construct the System Prompt ───
        job_title = session.job_title or "the position"
        candidate_name = f"{session.candidate.first_name} {session.candidate.last_name}" if session.candidate else "Candidate"
        round_designation = round_obj.get_designation_display() or round_obj.designation
        difficulty = round_obj.difficulty or "MID"
        max_questions = round_obj.max_questions or 10
        programming_language = round_obj.programming_language or ""

        prompt_system = f"""You are Sophia, an elite AI HR Interview Agent conducting a live voice interview for the position of "{job_title}".

INTERVIEW CONTEXT:
- Candidate Name: {candidate_name}
- Round: {round_designation}
- Difficulty Level: {difficulty}
- Maximum Questions: {max_questions}
"""
        if programming_language:
            prompt_system += f"- Programming Language Focus: {programming_language}\n"

        if session.job_description:
            jd_trimmed = session.job_description[:500] + "..." if len(session.job_description) > 500 else session.job_description
            prompt_system += f"- Job Description Context: {jd_trimmed}\n"

        if session.candidate_skills:
            prompt_system += f"- Candidate Skills: {session.candidate_skills}\n"

        prompt_system += f"""
YOUR BEHAVIOR:
1. You are a warm but professional interviewer. Speak naturally like a real human — use conversational language, brief affirmations ("Great point", "I see", "Interesting").
2. Only introduce yourself briefly in the initial greeting. For all subsequent turns, DO NOT introduce yourself, say 'I am Sophia', or mention you are an AI. Respond or ask the next question directly.
3. Listen carefully to the candidate's answer. Evaluate their response internally for:
   - Technical accuracy and depth
   - Communication clarity
   - Problem-solving approach
   - Relevance to the question
4. After each answer, provide brief acknowledgment, then ask a relevant follow-up question that digs deeper OR move to the next topic.
5. If the candidate's answer is vague or incomplete, probe deeper with clarifying questions like "Can you elaborate on that?" or "What specific approach would you take?"
6. If the candidate's answer demonstrates strong knowledge, challenge them with a harder follow-up.
7. Keep your responses concise — this is a voice conversation, not a lecture. Aim for 2-4 sentences per response.
8. Track the flow naturally. After covering {max_questions} question areas, wrap up the interview professionally.
9. NEVER reveal scores, evaluations, or internal assessment to the candidate.
10. NEVER break character. You are Sophia, the AI interviewer.

ROUND-SPECIFIC FOCUS for "{round_designation}":
- Ask questions directly relevant to this round type.
- For technical rounds: test frameworks, architecture, debugging, scalability.
- For HR rounds: cultural fit, teamwork, leadership, career goals.
- For coding rounds: algorithms, problem-solving methodology, complexity analysis.
- For behavioral rounds: situational questions, conflict resolution, past experience stories.
"""
        if programming_language:
            prompt_system += f"- For this coding round, prioritize evaluation and questions related to the {programming_language} programming language.\n"

        prompt_system += "\nBegin the interview now. (If this is the initial greeting, introduce yourself and ask the first question. If you are responding to a message in the chat history, do not introduce yourself again)."

        # Format dialogue history
        history_str = ""
        for msg in history:
            role = msg.get("role", "user")
            text = msg.get("text", "")
            if role in ["agent", "assistant", "model"]:
                history_str += f"Sophia: {text}\n"
            else:
                history_str += f"Candidate: {text}\n"

        # Ask the model to generate the response
        try:
            company = session.application.job.company if (session.application and session.application.job) else None
            model_name = AIBaseService.get_model_for_company(company)
            
            response_text = AIBaseService.generate_content(
                prompt=history_str + "Sophia:",
                system_instruction=prompt_system,
                temperature=0.7,
                model_name=model_name
            )
            
            # Clean up the output in case it includes "Sophia:" prefix
            if response_text.startswith("Sophia:"):
                response_text = response_text[len("Sophia:"):].strip()
                
            return self.build_response(
                "success",
                "Chat response generated successfully.",
                {"response": response_text}
            )
        except Exception as e:
            import logging
            logger = logging.getLogger("ai_interview.chat")
            logger.error(f"Fallback Chat call failed: {e}")
            return self.build_response(
                "error",
                f"Failed to generate AI chat response: {str(e)}",
                {},
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )
