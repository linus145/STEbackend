import json
import logging
from django.utils import timezone
from AIrounds.models import InterviewSession, InterviewRound, InterviewQuestion
from AIrounds.services.ai_base import AIBaseService
from AIrounds.services.prompt_service import InterviewPromptService

logger = logging.getLogger("ai_rounds.engine")

class InterviewEngineService:
    """Core logic for interacting with the AI model."""

    @staticmethod
    def generate_next_question(session_id, round_id):
        session = InterviewSession.objects.get(id=session_id)
        round_obj = InterviewRound.objects.get(id=round_id)
        previous_questions = InterviewQuestion.objects.filter(round=round_obj).order_by('asked_at')
        
        context = InterviewPromptService.build_interview_context(session, round_obj, previous_questions)
        prompt = f"Based on the following context, generate the next interview question.\n\nCONTEXT:\n{context}"
        
        response_text = AIBaseService.generate_content(
            prompt=prompt,
            system_instruction=InterviewPromptService.get_system_prompt(),
            temperature=0.7
        )
        
        try:
            data = json.loads(response_text)
            InterviewQuestion.objects.create(
                round=round_obj,
                question_text=data.get('question'),
                expected_topics=data.get('expected_topics', [])
            )
            return data
        except Exception as e:
            logger.error(f"Failed to parse AI question response: {e}")
            raise ValueError("AI failed to generate a valid question.")

    @staticmethod
    def evaluate_answer(session_id, round_id, question_id, answer_text):
        session = InterviewSession.objects.get(id=session_id)
        round_obj = InterviewRound.objects.get(id=round_id)
        question = InterviewQuestion.objects.get(id=question_id)
        
        # Update question with answer
        question.candidate_answer = answer_text
        question.answered_at = timezone.now()
        question.save()
        
        previous_questions = InterviewQuestion.objects.filter(round=round_obj).order_by('asked_at')
        context = InterviewPromptService.build_interview_context(session, round_obj, previous_questions)
        
        prompt = f"Evaluate the following answer given the context.\n\nANSWER:\n{answer_text}\n\nCONTEXT:\n{context}"
        
        response_text = AIBaseService.generate_content(
            prompt=prompt,
            system_instruction=InterviewPromptService.get_system_prompt(),
            temperature=0.3
        )
        
        try:
            data = json.loads(response_text)
            question.evaluation = data
            question.save()
            return data
        except Exception as e:
            logger.error(f"Failed to parse AI evaluation response: {e}")
            raise ValueError("AI failed to evaluate the answer.")

    @staticmethod
    def generate_round_summary(session_id, round_id):
        session = InterviewSession.objects.get(id=session_id)
        round_obj = InterviewRound.objects.get(id=round_id)
        previous_questions = InterviewQuestion.objects.filter(round=round_obj).order_by('asked_at')
        
        context = InterviewPromptService.build_interview_context(session, round_obj, previous_questions)
        prompt = f"The round is complete. Generate a FINAL_ROUND_SUMMARY based on the context.\n\nCONTEXT:\n{context}"
        
        response_text = AIBaseService.generate_content(
            prompt=prompt,
            system_instruction=InterviewPromptService.get_system_prompt(),
            temperature=0.3
        )
        
        try:
            data = json.loads(response_text)
            round_obj.round_score = data.get('overall_score', 0)
            round_obj.status = 'COMPLETED'
            round_obj.save()
            return data
        except Exception as e:
            logger.error(f"Failed to parse AI summary response: {e}")
            raise ValueError("AI failed to generate a round summary.")
    @staticmethod
    def generate_question_pool(application_id, round_type, designation, difficulty, question_format='TEXT', programming_language='', count=5):
        from jobs.models import JobApplication
        application = JobApplication.objects.get(id=application_id)
        
        context = InterviewPromptService.build_config_context(application, round_type, designation, difficulty)
        
        # Build format-specific instructions
        format_instruction = ""
        if question_format == 'MCQ':
            format_instruction = (
                "Each question MUST be a multiple-choice question with 4 options (A, B, C, D). "
                "Return each question as a string that includes the options. "
                "Format: 'Question text\\nA) Option A\\nB) Option B\\nC) Option C\\nD) Option D'"
            )
        elif question_format == 'MULTI_SELECT':
            format_instruction = (
                "Each question MUST be a multiple-select question (more than one correct answer). "
                "Include 4-5 options. Format: 'Question text\\nA) Option A\\nB) Option B\\nC) Option C\\nD) Option D\\nE) Option E'"
            )
        elif question_format == 'CODE':
            lang_note = f" in {programming_language}" if programming_language else ""
            format_instruction = (
                f"Each question MUST be a coding/programming problem{lang_note}. "
                "Include clear input/output specifications. "
                "Questions should test algorithmic thinking, problem-solving, and code quality."
            )
        else:
            format_instruction = "Each question should be an open-ended text question requiring a written answer."
        
        prompt = (
            f"Generate exactly {count} interview questions for a '{designation}' round "
            f"at '{difficulty}' difficulty level.\n\n"
            f"QUESTION FORMAT: {format_instruction}\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"IMPORTANT: Return ONLY a JSON object with a single key 'questions' containing "
            f"an array of exactly {count} question strings. Example:\n"
            f'{{"questions": ["Question 1?", "Question 2?"]}}'
        )
        
        system_prompt = (
            "You are an expert interview question generator. "
            "Generate role-specific, relevant questions based on the candidate's resume and the job description. "
            "Return ONLY valid JSON with the key 'questions' containing an array of question strings. "
            "No markdown, no extra text."
        )
        
        logger.info(f"Generating {count} questions: designation={designation}, format={question_format}, lang={programming_language}")
        
        response_text = AIBaseService.generate_content(
            prompt=prompt,
            system_instruction=system_prompt,
            temperature=0.8
        )
        
        logger.info(f"AI raw response (first 500 chars): {response_text[:500] if response_text else 'EMPTY'}")
        
        try:
            data = json.loads(response_text)
            questions = data.get('questions', [])
            if not questions:
                if isinstance(data, list):
                    questions = data
                else:
                    logger.warning(f"Unexpected AI response structure: {list(data.keys())}")
            return questions
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}\nRaw: {response_text[:300]}")
            raise ValueError("AI failed to generate valid questions. Please try again.")
