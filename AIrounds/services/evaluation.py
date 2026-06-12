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

    round_type: str = Field(description="The type of round (MCQ, MULTI_SELECT, TEXT, CODE, VIDEO)")
    score: int = Field(description="The evaluated score out of 10 based on scoring rules")
    technical_score: int = Field(description="Technical score (0-10)")
    accuracy_score: int = Field(description="Accuracy score (0-10)")
    communication_score: int = Field(description="Communication score (0-10)")
    reasoning_score: int = Field(description="Reasoning score (0-10)")
    overall_score: int = Field(description="Overall score (0-10)")
    topic_mastery: str = Field(description="Topic mastery level")
    strengths: list[str] = Field(description="Strengths of the response")
    weaknesses: list[str] = Field(description="Weaknesses or gaps in the response")
    key_points_missed: list[str] = Field(description="Key points missed by the candidate")
    verified_concepts: list[str] = Field(description="Concepts successfully verified by the response")
    missing_concepts: list[str] = Field(description="Concepts missing or incorrect in the response")
    feedback: str = Field(description="Detailed constructive feedback")
    evaluation_summary: str = Field(description="Summary of the evaluation")


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

AI_EVALUATION_SYSTEM_INSTRUCTION = "You are an Enterprise Examination Evaluation Engine."


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

        company = session.application.job.company if (session.application and session.application.job) else None
        model_name = AIBaseService.get_model_for_company(company)

        return InterviewEvaluationService._evaluate_with_ai(
            session, round_obj, question, answer_text, normalized_type, model_name=model_name
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

        company = session.application.job.company if (session.application and session.application.job) else None
        model_name = AIBaseService.get_model_for_company(company)
        is_gemini = model_name not in ("kimi", "Kimi-K2.6", "grok", "grok-4-20-non-reasoning", "grok-4.20-non-reasoning", "grok-4-1-fast-non-reasoning", "grok-4.1-non-reasoning")
        
        if not is_gemini:
            prompt += (
                "\n\nYou must return a JSON object exactly matching this structure:\n"
                "{\n"
                '  "type": "FINAL_ROUND_SUMMARY",\n'
                '  "round_type": "...",\n'
                '  "overall_score": 0,\n'
                '  "technical_depth": "...",\n'
                '  "communication_assessment": "...",\n'
                '  "problem_solving_assessment": "...",\n'
                '  "strengths": [],\n'
                '  "weaknesses": [],\n'
                '  "risk_indicators": [],\n'
                '  "recommended_decision": "...",\n'
                '  "interview_summary": "..."\n'
                "}\n"
            )

        response_text = AIBaseService.generate_content(
            prompt=prompt,
            system_instruction=InterviewPromptService.get_system_prompt(),
            temperature=0.3,
            model_name=model_name
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
            "score": final_score,
            "technical_score": final_score,
            "accuracy_score": final_score,
            "communication_score": final_score,
            "reasoning_score": final_score,
            "overall_score": final_score,
            "topic_mastery": topic_mastery,
            "strengths": ["Correct option selected."] if is_correct else [],
            "weaknesses": [] if is_correct else ["Incorrect option selection."],
            "key_points_missed": [],
            "verified_concepts": [],
            "missing_concepts": [],
            "feedback": feedback,
            "evaluation_summary": feedback,
        }

        question.evaluation = evaluation_result
        question.score = final_score
        question.save()

        return evaluation_result

    # ──────────────────────────────────────────────
    # PRIVATE: AI-based evaluation (TEXT / CODE / VIDEO)
    # ──────────────────────────────────────────────

    @staticmethod
    def _evaluate_with_ai(session, round_obj, question, answer_text, normalized_type, model_name=None):
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

        if not model_name:
            company = session.application.job.company if (session.application and session.application.job) else None
            model_name = AIBaseService.get_model_for_company(company)

        ideal_answer = question.ideal_answer or "No ideal answer provided."
        expected_topics = ", ".join(question.expected_topics) if isinstance(question.expected_topics, list) else "None"
        mcq_options = json.dumps(question.mcq_options) if question.mcq_options else "None"

        prompt = f"""You are an Enterprise Examination Evaluation Engine.

Your responsibility is to evaluate candidate responses strictly according to the ROUND_TYPE.

==================================================
INPUT
=====

ROUND_TYPE:
{round_type}

QUESTION:
{question.question_text}

IDEAL_ANSWER:
{ideal_answer}

EXPECTED_TOPICS:
{expected_topics}

CANDIDATE_ANSWER:
{candidate_answer}

MCQ_OPTIONS:
{mcq_options}

==================================================
ROUND TYPE RULES
================

IF ROUND_TYPE = MCQ

* Evaluate option selection only.
* If selected option matches correct option exactly:
  score = full marks.
* Otherwise:
  score = zero.
* Do not use subjective evaluation.

---

IF ROUND_TYPE = MULTI_SELECT

* Compare candidate selections against correct answers.
* Award partial marks proportional to correct selections.
* Deduct marks for incorrect selections.
* Never award full marks unless all correct options are selected.

---

IF ROUND_TYPE = TEXT

Evaluate:

* Technical correctness
* Conceptual understanding
* Completeness
* Relevance
* Practical understanding
* Logical reasoning
* Clarity

Determine:

* What was answered correctly.
* What was missed.
* What misconceptions exist.

---

IF ROUND_TYPE = CODE

Evaluate:

* Functional correctness
* Algorithm quality
* Edge case handling
* Complexity analysis
* Security
* Readability
* Maintainability
* Modularity

Detect:

* Syntax issues
* Logical bugs
* Anti-patterns

---

IF ROUND_TYPE = VIDEO

Evaluate:

* Communication
* Technical knowledge
* Confidence
* Articulation
* Problem solving
* Leadership indicators

==================================================
SCORING RULES
=============

0-10 scale.

10 = Perfect answer

8-9 = Strong answer

6-7 = Good answer

4-5 = Partial understanding

2-3 = Weak understanding

0-1 = Incorrect answer

Never score based on answer length.

Never score based on keywords alone.

Always evaluate actual understanding.

==================================================
RETURN JSON ONLY
================
"""

        is_gemini = model_name not in ("kimi", "Kimi-K2.6", "grok", "grok-4-20-non-reasoning", "grok-4.20-non-reasoning", "grok-4-1-fast-non-reasoning", "grok-4.1-non-reasoning")
        if not is_gemini:
            prompt += (
                "\n\nYou must return a JSON object exactly matching this structure:\n"
                "{\n"
                '  "round_type": "...", \n'
                '  "score": 0, \n'
                '  "technical_score": 0, \n'
                '  "accuracy_score": 0, \n'
                '  "communication_score": 0, \n'
                '  "reasoning_score": 0, \n'
                '  "overall_score": 0, \n'
                '  "topic_mastery": "...", \n'
                '  "strengths": [], \n'
                '  "weaknesses": [], \n'
                '  "key_points_missed": [], \n'
                '  "verified_concepts": [], \n'
                '  "missing_concepts": [], \n'
                '  "feedback": "...", \n'
                '  "evaluation_summary": "..."\n'
                "}\n"
            )

        response_text = AIBaseService.generate_content(
            prompt=prompt,
            system_instruction=AI_EVALUATION_SYSTEM_INSTRUCTION,
            temperature=0.3,
            response_schema=AnswerEvaluation,
            model_name=model_name
        )

        try:
            data = json.loads(response_text)
            question.evaluation = data
            question.save()
            return data
        except Exception as e:
            logger.error(f"Failed to parse AI evaluation response: {e}")
            raise ValueError("AI failed to evaluate the answer.")
