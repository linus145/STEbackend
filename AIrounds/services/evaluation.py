import re
import json
import logging
from django.utils import timezone
from pydantic import BaseModel, Field
from AIrounds.models import InterviewSession, InterviewRound, InterviewQuestion
from AIrounds.services.ai_base import AIBaseService
from AIrounds.services.prompt_service import InterviewPromptService

logger = logging.getLogger("ai_rounds.evaluation")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pydantic Schema — AI Evaluation Response
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AnswerEvaluation(BaseModel):
    """Schema for the AI evaluation response returned by Gemini."""

    # Core backwards compatibility fields
    score: int = Field(description="The overall score awarded to the candidate out of the maximum marks (out of 10, proportional to overall_score)")
    feedback: str = Field(description="Constructive, professional feedback on the candidate's answer and evaluation reasoning combined")
    key_points_missed: list[str] = Field(description="Key points or areas for improvement that the candidate missed, if any (must be empty for MCQ/options)")

    # Enterprise Evaluation Engine fields
    round_type: str = Field(description="The type of round being evaluated (e.g. TEXT, MCQ, MULTI_SELECT, CODE, VIDEO)")
    technical_score: int = Field(description="Score for technical depth and correctness (0-10)")
    communication_score: int = Field(description="Score for communication clarity and articulation (0-10)")
    problem_solving_score: int = Field(description="Score for problem-solving capability (0-10)")
    confidence_score: int = Field(description="Score for confidence level and certainty (0-10)")
    architecture_score: int = Field(description="Score for architectural design and modularity, applicable for coding/system design (0-10)")
    security_score: int = Field(description="Score for security and performance optimization (0-10)")
    behavioral_score: int = Field(description="Score for behavioral fit and leadership indicators (0-10)")
    overall_score: int = Field(description="The aggregated overall score (0-10)")
    candidate_level_detected: str = Field(description="Claimed seniority level detected (Junior, Mid, Senior, Lead/Staff)")
    topic_mastery: str = Field(description="Mastery level of the evaluated topic (e.g. Expert, Proficient, Vague, Shallow)")
    strengths: list[str] = Field(description="Key strengths demonstrated in the response")
    weaknesses: list[str] = Field(description="Weaknesses or technical gaps detected in the answer")
    verified_skills: list[str] = Field(description="List of skills successfully verified by this answer")
    missing_skills: list[str] = Field(description="Skills that remain unverified or missing")
    red_flags: list[str] = Field(description="Any red flags, keyword stuffing, AI-generated styles, or bluffing detected")
    cheating_probability: int = Field(description="Probability of cheating or copying (0 to 100)")
    ai_generated_probability: int = Field(description="Probability of AI-generated answers or memorized tutorials (0 to 100)")
    improvement_areas: list[str] = Field(description="Specific actionable areas where the candidate needs improvement")
    follow_up_reason: str = Field(description="Reason why a follow-up question is generated or required")
    next_question: str = Field(description="An intelligent, conversational follow-up question that challenges any shallow claims")
    final_recommendation: str = Field(description="Final recommendation detail for hiring managers")
    hire_decision: str = Field(description="Final hire decision status (e.g. HIRE, NO-HIRE, WATCH)")
    confidence_summary: str = Field(description="Summary detailing the candidate's confidence pattern")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MCQ_TYPES = [
    'MCQ',
    'MULTIPLE_CHOICE',
    'MULTIPLE CHOICE',
    'MULTIPLE_CHOICE_SINGLE',
    'MULTIPLE_CHOICE_MULTIPLE',
    'MULTI_SELECT',
    'SINGLE_ANSWER',
    'MULTIPLE_ANSWER',
    'MULTIPLE CHOICE (SINGLE ANSWER)',
    'MULTIPLE CHOICE (MULTIPLE ANSWERS)',
]

AI_EVALUATION_SYSTEM_INSTRUCTION = (
    "You are an Enterprise-Level Autonomous AI Interview Evaluation Engine.\n\n"
    "Your responsibility is to evaluate candidate answers with industry-grade hiring intelligence standards similar to senior recruiters, technical architects, and enterprise HR panels.\n\n"
    "You are NOT a chatbot.\n"
    "You are NOT a simple scorer.\n"
    "You are a professional AI hiring evaluator.\n\n"
    "GLOBAL EVALUATION RULES:\n"
    "1. Always evaluate: technical depth, correctness, communication, reasoning, confidence, real-world understanding, problem-solving, seniority indicators, and consistency.\n"
    "2. Detect: vague answers, memorized/tutorial responses, keyword stuffing, bluffing, hallucinated technical claims, AI-generated generic responses, and cheating indicators.\n"
    "3. Never score based only on keywords.\n"
    "4. Evaluate contextually based on: role, seniority, interview stage, round type, candidate history, and previous answers.\n"
    "5. Adapt scoring expectations dynamically: junior, mid-level, senior, lead/staff.\n"
    "6. Maintain enterprise hiring standards.\n"
    "7. Focus on realistic recruiter-level evaluation quality.\n"
    "8. Behave like a senior technical hiring panel."
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _safe_parse_skills(candidate_skills):
    """Safely converts candidate_skills (JSONField — could be list, str, or None) into a display string."""
    if not candidate_skills:
        return "None"
    if isinstance(candidate_skills, list):
        return ", ".join(str(s) for s in candidate_skills)
    if isinstance(candidate_skills, str):
        return ", ".join(s.strip() for s in candidate_skills.split(','))
    return str(candidate_skills)


def _clean_json_string(text):
    """Cleans AI response text to ensure it's valid JSON."""
    if not text:
        return ""

    # 1. Remove markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    text = text.strip()

    # 2. Try direct parse first
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    # 3. Fix unescaped control chars and literal backslashes inside JSON string values
    def _escape_strings(raw):
        result = []
        in_string = False
        i = 0
        while i < len(raw):
            ch = raw[i]
            if ch == '"' and (i == 0 or raw[i-1] != '\\'):
                in_string = not in_string
                result.append(ch)
            elif in_string:
                if ch == '\n':
                    result.append('\\n')
                elif ch == '\r':
                    result.append('\\r')
                elif ch == '\t':
                    result.append('\\t')
                elif ch == '\\':
                    if i + 1 < len(raw) and raw[i+1] in ['"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u']:
                        result.append(ch)
                    else:
                        result.append('\\\\')
                else:
                    result.append(ch)
            else:
                result.append(ch)
            i += 1
        return ''.join(result)

    fixed = _escape_strings(text)
    try:
        json.loads(fixed)
        return fixed
    except (json.JSONDecodeError, ValueError):
        pass

    # 4. Last resort: extract JSON object boundaries
    json_start = text.find('{')
    json_end = text.rfind('}')
    if json_start != -1 and json_end != -1:
        extracted = text[json_start:json_end + 1]
        fixed2 = _escape_strings(extracted)
        try:
            json.loads(fixed2)
            return fixed2
        except (json.JSONDecodeError, ValueError):
            pass

    return text


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Service
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class InterviewEvaluationService:
    """Handles all answer evaluation and round summary logic."""

    # ──────────────────────────────────────────────
    # PUBLIC: Evaluate a single answer
    # ──────────────────────────────────────────────

    @staticmethod
    def evaluate_answer(session_id, round_id, question_id, answer_text):
        session = InterviewSession.objects.get(id=session_id)
        round_obj = InterviewRound.objects.get(id=round_id)
        question = InterviewQuestion.objects.get(id=question_id)

        # Persist candidate answer
        question.candidate_answer = answer_text
        question.answered_at = timezone.now()
        question.save()

        # Determine question type / round category
        normalized_type = (question.question_type or round_obj.question_format or '').strip().upper()

        # Route to the correct evaluator
        is_option_based = (
            normalized_type in [t.upper() for t in MCQ_TYPES]
            or (isinstance(question.mcq_options, list) and len(question.mcq_options) > 0)
        )

        if is_option_based:
            return InterviewEvaluationService._evaluate_mcq(
                question, round_obj, answer_text, normalized_type
            )

        return InterviewEvaluationService._evaluate_with_ai(
            session, round_obj, question, answer_text, normalized_type
        )

    # ──────────────────────────────────────────────
    # PUBLIC: Generate round summary
    # ──────────────────────────────────────────────

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
            cleaned_text = _clean_json_string(response_text)
            data = json.loads(cleaned_text)
            round_obj.round_score = data.get('overall_score', 0)
            round_obj.status = 'COMPLETED'
            round_obj.save()
            return data
        except Exception as e:
            logger.error(f"Failed to parse AI summary response: {e}")
            raise ValueError("AI failed to generate a round summary.")

    # ──────────────────────────────────────────────
    # PRIVATE: Programmatic MCQ / Multi-select
    # ──────────────────────────────────────────────

    @staticmethod
    def _evaluate_mcq(question, round_obj, answer_text, normalized_type):
        """Evaluates MCQ/MULTI_SELECT answers programmatically — no LLM call needed."""

        correct_options = []
        correct_options_details = []

        if isinstance(question.mcq_options, list):
            for opt in question.mcq_options:
                if opt.get("is_correct") is True:
                    label = str(opt.get("label", "")).strip().upper()
                    text = str(opt.get("text", "")).strip()
                    correct_options.append(label)
                    correct_options_details.append(f"{label}) {text}")

        # Ensure ideal answer shows which option is correct
        if correct_options_details:
            question.ideal_answer = f"The correct answer is: {', '.join(correct_options_details)}"

        candidate_raw = str(answer_text or "").strip().upper()

        # Extract labels safely
        selected_labels = set(re.findall(r'\b[A-Z]\b', candidate_raw))
        if not selected_labels:
            selected_labels = set(
                item.strip()
                for item in re.split(r'[,\s;]+', candidate_raw)
                if item.strip()
            )

        correct_set = set(correct_options)

        # Detect multi-answer automatically
        is_multi_answer = len(correct_set) > 1 or 'MULTI' in normalized_type

        # ── Score calculation ──
        if not is_multi_answer:
            is_correct = len(correct_set) == 1 and selected_labels == correct_set
            final_score = question.marks if is_correct else 0
        else:
            total_correct = len(correct_set)
            matched_correct = len(selected_labels & correct_set)
            wrong_selected = len(selected_labels - correct_set)
            partial_ratio = matched_correct / total_correct if total_correct else 0
            penalty = wrong_selected * 0.25
            computed_score = max(partial_ratio - penalty, 0)
            final_score = round(question.marks * computed_score)
            is_correct = selected_labels == correct_set

        # Build selected option text
        selected_options_details = []
        if isinstance(question.mcq_options, list):
            for label in sorted(selected_labels):
                for opt in question.mcq_options:
                    if str(opt.get("label", "")).strip().upper() == label:
                        selected_options_details.append(f"{label}) {opt.get('text', '')}")

        question.candidate_answer = (
            ", ".join(selected_options_details)
            if selected_options_details
            else answer_text
        )

        # ── Feedback ──
        if is_correct:
            feedback = (
                f"Correct answer selected. "
                f"Candidate selected the correct option(s): "
                f"{', '.join(correct_options_details)}."
            )
            topic_mastery = "Excellent"
        elif final_score > 0:
            feedback = "Partially correct answer selected."
            topic_mastery = "Partial"
        else:
            feedback = (
                f"Incorrect answer selected. "
                f"Correct option(s): {', '.join(correct_options_details)}."
            )
            topic_mastery = "Weak"

        # ── Build evaluation result ──
        evaluation_result = {
            "round_type": normalized_type,
            "technical_score": final_score,
            "communication_score": final_score,
            "problem_solving_score": final_score,
            "confidence_score": final_score,
            "architecture_score": final_score,
            "security_score": final_score,
            "behavioral_score": final_score,
            "overall_score": final_score,
            "score": final_score,
            "feedback": feedback,
            "key_points_missed": [],
            "candidate_level_detected": round_obj.difficulty or "MID",
            "topic_mastery": topic_mastery,
            "strengths": ["Correct option selected."] if is_correct else [],
            "weaknesses": [] if is_correct else ["Incorrect option selection."],
            "verified_skills": [],
            "missing_skills": [],
            "red_flags": [],
            "cheating_probability": 0,
            "ai_generated_probability": 0,
            "improvement_areas": [],
            "follow_up_reason": "",
            "next_question": "",
            "final_recommendation": feedback,
            "hire_decision": "HIRE" if final_score >= (question.marks * 0.7) else "NO-HIRE",
            "confidence_summary": "Candidate selected option(s) confidently.",
            "breakdown": {
                "accuracy": final_score,
                "depth": final_score,
                "relevance": final_score,
            },
        }

        question.evaluation = evaluation_result
        question.score = final_score
        question.save()

        return evaluation_result

    # ──────────────────────────────────────────────
    # PRIVATE: AI-based evaluation (TEXT / CODE / VIDEO)
    # ──────────────────────────────────────────────

    @staticmethod
    def _evaluate_with_ai(session, round_obj, question, answer_text, normalized_type):
        """Evaluates TEXT, CODE, or VIDEO answers using AI (Gemini)."""

        previous_questions = InterviewQuestion.objects.filter(round=round_obj).order_by('asked_at')
        context = InterviewPromptService.build_interview_context(session, round_obj, previous_questions)

        # Build variables dynamically
        role = session.job_title or "Software Engineer"
        experience_level = round_obj.difficulty or "Mid-Level"
        round_type = normalized_type
        expected_skills = ", ".join(question.expected_topics) if isinstance(question.expected_topics, list) else "Technical concepts"
        candidate_answer = answer_text
        previous_conversation = context
        skills_verified = _safe_parse_skills(session.candidate_skills)
        current_topic = question.question_text

        prompt = f"""Evaluate the candidate's answer using the Enterprise AI Interview Evaluation Engine specifications.

==================================================
INPUT VARIABLES
==================================================

ROLE:
{role}

EXPERIENCE_LEVEL:
{experience_level}

ROUND_TYPE:
{round_type}

QUESTION:
{question.question_text}

EXPECTED_SKILLS:
{expected_skills}

CANDIDATE_ANSWER:
{candidate_answer}

PREVIOUS_CONVERSATION:
{previous_conversation}

SKILLS_ALREADY_VERIFIED:
{skills_verified}

CURRENT_TOPIC:
{current_topic}

==================================================
EVALUATION LOGIC TO EXECUTE:
==================================================
For {round_type} Round Type:
- TEXT / TYPING / CODE:
  - Technical accuracy, structuring, scalability, optimizations, modularity, code quality, naming conventions, and anti-patterns.
  - Assess if the answer matched the correct concepts fully or partially. Give the marks based upon the candidate's typed answer.
  - Determine junior/mid/senior level indicators.

- AI VOICE / VIDEO:
  - Articulation depth, problem-solving, confidence, leadership, hesitation patterns, masteries.

==================================================
STRICT SCHEMATIC FIELD ALIGNMENT RULES:
==================================================
- 'score': Must be an integer scale out of 10 representing the main marks (proportional to overall_score, e.g. 0 to 10). If the candidate is fully correct, give 10/10. If partially related, grade accordingly (e.g. 5/10).
- 'feedback': Constructive feedback detailing your reasoning and overall hiring summary.
- 'key_points_missed': Specific checklist of key missing items/improvement areas.
- Ensure all other schema fields (red_flags, verified_skills, weaknesses, next_question, hire_decision, overall_score, technical_score, etc.) are strictly populated according to the schema!
"""

        response_text = AIBaseService.generate_content(
            prompt=prompt,
            system_instruction=AI_EVALUATION_SYSTEM_INSTRUCTION,
            temperature=0.3,
            response_schema=AnswerEvaluation,
        )

        try:
            data = json.loads(response_text)
            question.evaluation = data
            question.save()
            return data
        except Exception as e:
            logger.error(f"Failed to parse AI evaluation response: {e}")
            raise ValueError("AI failed to evaluate the answer.")
