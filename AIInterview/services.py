import json
import logging
from django.utils import timezone
from django.conf import settings as dj_settings
from AIrounds.models import CandidateInterviewLink, InterviewRound, InterviewQuestion
from AIrounds.services.ai_base import AIBaseService

logger = logging.getLogger(__name__)

class AIInterviewService:
    """
    Core service class containing the settings generation, prompt construction,
    voice transcript splitting, and automated/AI evaluation logic for the AIInterview app.
    """

    @staticmethod
    def generate_agent_settings(exam_token, round_id):
        """
        Validates exam token and round ID, and generates the complete Deepgram Voice Agent
        settings payload including dynamic prompt construction.
        """
        try:
            link = CandidateInterviewLink.objects.select_related(
                "session", "session__candidate"
            ).get(token=exam_token)
        except CandidateInterviewLink.DoesNotExist:
            raise ValueError("Invalid exam token.")

        if not link.is_valid:
            if link.status not in ["ACTIVE", "STARTED"]:
                raise ValueError("This exam link has expired or already been completed.")

        session = link.session

        try:
            round_obj = session.rounds.get(id=round_id)
        except InterviewRound.DoesNotExist:
            raise ValueError("Interview round not found for this session.")

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

        # ─── Construct Settings JSON payload ───
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

        # Securely configure the custom OpenAI-compatible Google endpoint
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
            settings_payload["agent"]["think"]["provider"]["type"] = "google"
            settings_payload["agent"]["think"]["provider"]["model"] = "gemini-2.5-flash"

        return settings_payload

    @staticmethod
    def split_voice_transcript(transcript, model_name="gemini-2.5-flash"):
        """
        Parses a dynamic voice dialogue transcript into structured question-answer pairs using Gemini.
        """
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
            logger.error(f"Failed to split voice transcript in AIInterviewService: {e}")
            return [{"question": "Voice Interview Session", "answer": transcript}]

    @staticmethod
    def save_split_transcript(question_id, pairs):
        """
        Saves the split segments into separate InterviewQuestion database records.
        """
        try:
            question = InterviewQuestion.objects.select_related('round').get(id=question_id)
        except InterviewQuestion.DoesNotExist:
            logger.error(f"Question {question_id} not found during split save.")
            return

        if isinstance(pairs, list) and len(pairs) > 0:
            # 1. Update the first (existing) question
            first_pair = pairs[0]
            question.question_text = first_pair.get("question", question.question_text)
            question.candidate_answer = first_pair.get("answer", "")
            question.answered_at = timezone.now()
            question.save(update_fields=['question_text', 'candidate_answer', 'answered_at'])

            # 2. Clear other questions in this round
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
            logger.warning(f"No valid pairs received to split for question {question_id}.")

    @staticmethod
    def evaluate_question_logic(question_id):
        """
        Evaluates a single question.
        - Programmatic evaluation for MCQ/MULTI_SELECT (no LLM, 100% accurate, no explanation needed).
        - AI-based evaluation for TEXT, CODE, or VIDEO (uses Gemini).
        """
        try:
            question = InterviewQuestion.objects.select_related('round__session').get(id=question_id)
        except InterviewQuestion.DoesNotExist:
            raise ValueError("Question not found.")

        if not question.candidate_answer:
            raise ValueError("No candidate answer to evaluate.")

        # ─── 1. Programmatic Evaluation for MCQ/MULTI_SELECT ───
        if question.question_type in ['MCQ', 'MULTI_SELECT']:
            correct_options = []
            if isinstance(question.mcq_options, list):
                for opt in question.mcq_options:
                    if opt.get("is_correct") is True:
                        correct_options.append(opt.get("label", "").strip().upper())
            
            cand_ans_clean = question.candidate_answer.strip().upper()
            
            # Simple direct matching: e.g. "A" matches ["A"]
            is_correct = False
            for correct_label in correct_options:
                if correct_label in cand_ans_clean or cand_ans_clean in correct_label:
                    is_correct = True
                    break
            
            if is_correct:
                score = question.marks
                feedback = f"Correct option selected. Option labels matched: {', '.join(correct_options)}."
            else:
                score = 0
                feedback = f"Incorrect option selected. Correct options were: {', '.join(correct_options)}."
            
            evaluation_result = {
                "score": score,
                "feedback": feedback,
                "breakdown": {
                    "accuracy": 10 if is_correct else 0,
                    "depth": 10 if is_correct else 0,
                    "relevance": 10 if is_correct else 0
                }
            }
            question.evaluation = evaluation_result
            question.save(update_fields=['evaluation'])
            return evaluation_result

        # ─── 2. AI-based Evaluation for TEXT, CODE, or VIDEO ───
        session = question.round.session
        round_obj = question.round
        previous_questions = InterviewQuestion.objects.filter(round=round_obj).order_by('asked_at')
        from AIrounds.services.prompt_service import InterviewPromptService
        context = InterviewPromptService.build_interview_context(session, round_obj, previous_questions)
        
        evaluation_rules = (
            "CRITICAL EVALUATION RULE FOR TYPING/SPOKEN ANSWERS:\n"
            "- Evaluate the candidate's answer based on technical correctness, explanation depth, clarity, and relevance.\n"
            "- Be rigorous and fair."
        )

        prompt = (
            f"Evaluate the candidate's answer against the provided ideal answer/criteria.\n\n"
            f"QUESTION: {question.question_text}\n"
            f"IDEAL ANSWER: {question.ideal_answer or 'Not provided. Evaluate based on industry best practices for this role and question context.'}\n"
            f"CANDIDATE ANSWER: {question.candidate_answer}\n\n"
            f"{evaluation_rules}\n\n"
            f"CONTEXT:\n{context}"
        )

        from AIrounds.services.evaluation import AnswerEvaluation
        response_text = AIBaseService.generate_content(
            prompt=prompt,
            system_instruction="You are an expert interviewer evaluating a candidate's response. Be fair but rigorous.",
            temperature=0.3,
            response_schema=AnswerEvaluation
        )

        try:
            data = json.loads(response_text)
            question.evaluation = data
            question.save(update_fields=['evaluation'])
            return data
        except Exception as e:
            logger.error(f"Failed to parse AI evaluation response: {e}")
            raise ValueError("AI failed to evaluate the answer.")
