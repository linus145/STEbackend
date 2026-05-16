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
    def _clean_json_string(text):
        """Cleans AI response text to ensure it's valid JSON."""
        import re
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
            """Walk through the string char by char, escaping control chars and solo backslashes inside quotes."""
            result = []
            in_string = False
            i = 0
            while i < len(raw):
                ch = raw[i]
                
                # Toggle in_string state on unescaped quotes
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
                        # If it's a backslash, check if it's followed by a valid escape char
                        # Valid JSON escapes: ", \, /, b, f, n, r, t, u
                        if i + 1 < len(raw) and raw[i+1] in ['"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u']:
                            result.append(ch) # Keep as is, it's a valid escape sequence
                        else:
                            result.append('\\\\') # Escape the literal backslash
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
            cleaned_text = InterviewEngineService._clean_json_string(response_text)
            data = json.loads(cleaned_text)
            InterviewQuestion.objects.create(
                round=round_obj,
                question_text=data.get('question'),
                ideal_answer=data.get('ideal_answer'),
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
        
        prompt = (
            f"Evaluate the candidate's answer against the provided ideal answer/criteria.\n\n"
            f"QUESTION: {question.question_text}\n"
            f"IDEAL ANSWER: {question.ideal_answer or 'Not provided. Evaluate based on industry best practices for this role and question context.'}\n"
            f"CANDIDATE ANSWER: {answer_text}\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"IMPORTANT: Return a JSON object with 'score' (out of {question.marks}), 'feedback', and 'key_points_missed' (array)."
        )
        
        response_text = AIBaseService.generate_content(
            prompt=prompt,
            system_instruction="You are an expert interviewer evaluating a candidate's response. Be fair but rigorous.",
            temperature=0.3
        )
        
        try:
            cleaned_text = InterviewEngineService._clean_json_string(response_text)
            data = json.loads(cleaned_text)
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
            cleaned_text = InterviewEngineService._clean_json_string(response_text)
            data = json.loads(cleaned_text)
            round_obj.round_score = data.get('overall_score', 0)
            round_obj.status = 'COMPLETED'
            round_obj.save()
            return data
        except Exception as e:
            logger.error(f"Failed to parse AI summary response: {e}")
            raise ValueError("AI failed to generate a round summary.")
    # Maps round designations to their specific question focus areas
    # This ensures AI generates the RIGHT kind of questions for each designation
    DESIGNATION_FOCUS = {
        "APTITUDE_ROUND": "numerical reasoning, quantitative aptitude. TOPICS: Number System (Prime, divisibility, unit digits, LCM/HCF), Arithmetic (Percentages, profit/loss, SI/CI, averages, ratios, partnerships, mixtures), Time/Distance (Trains, boats, races), Work/Efficiency (Pipes, wages), Modern Math (Permutations, probability, set theory), Algebra/Geometry (Equations, AP/GP, area/volume, surface area), Data Interpretation (Bar/Pie/Line graphs, tables, caselets). NO coding, NO programming. GENERATION_RULES: Randomly pick exactly 1 subtopic per call. Dynamically generate randomized names and values. Provide 4 unique options, a step-by-step solution, and a single marked correct answer. Avoid standard textbook numbers.",
        "LOGICAL_REASONING": "logical puzzles. TOPICS: Arrangements (Linear/Circular seating, matrix, floor puzzles), Blood Relations, Direction Sense (Shadow problems, compass), Coding-Decoding, Sequence/Series (Number/Letter series, Clocks/Calendars, Leap years), Ranking/Order, Syllogisms (Venn diagrams), Critical Reasoning (Assumptions, Cause/Effect, Arguments), Verbal Logic (Analogies, Odd-one-out), Non-Verbal (Mirror/Water images, Paper folding/cutting, Cubes/Dice, Embedded figures). NO coding, NO programming. GENERATION_RULES: Randomly pick 1 topic. For arrangements, strictly map out the logical matrix internally first to ensure there is exactly one mathematically valid solution. Do not create paradoxes.",
        "COMMUNICATION_ROUND": "verbal ability, comprehension, grammar, articulation, presentation skills, email writing, summarization. NO coding, NO programming. GENERATION_RULES: Provide a random workplace context (e.g., dealing with an angry client, announcing a delay) and ask the candidate to draft a response or summarize a 200-word block of text.",
        "HR_SCREENING": "motivation, career goals, salary expectations, notice period, relocation, company culture fit. NO technical, NO coding.",
        "BEHAVIORAL_ROUND": "past behavior scenarios (STAR method), conflict resolution, teamwork, leadership, handling pressure. NO technical, NO coding.",
        "SITUATIONAL_ROUND": "hypothetical workplace scenarios, decision making, ethical dilemmas, priority management. NO coding.",
        "CULTURAL_FIT": "values alignment, team dynamics, work style, company mission fit. NO technical, NO coding.",
        "LEADERSHIP_ROUND": "leadership style, team management, mentoring, strategic thinking, people management. NO coding.",
        "TECHNICAL_SCREENING": "technical concepts, theory, architecture, design patterns, best practices relevant to the job role.",
        "TECHNICAL_INTERVIEW": "deep technical knowledge, system internals, framework understanding, debugging scenarios relevant to the job.",
        "CODING_ROUND": "coding problems, algorithms, data structures, problem-solving with code.",
        "LIVE_CODING": "real-time coding challenges, pair programming scenarios, live implementation.",
        "MACHINE_CODING": "build a small module/feature from scratch, design + implement solution.",
        "DEBUGGING_ROUND": "find and fix bugs in code, identify issues in given code snippets.",
        "SYSTEM_DESIGN": "system architecture, scalability, distributed systems, caching, load balancing, database design.",
        "ARCHITECTURE_ROUND": "software architecture patterns, microservices, monolith vs distributed, tech stack decisions.",
        "CASE_STUDY": "business case analysis, problem decomposition, solution design, trade-off analysis.",
        "PRODUCT_THINKING": "product sense, feature prioritization, user empathy, metrics, A/B testing.",
        "SALARY_NEGOTIATION": "compensation discussion, benefits, equity, counter-offer handling.",
        "OFFER_DISCUSSION": "offer details, joining date, relocation, team introduction.",
    }

    @staticmethod
    def generate_question_pool(application_id, round_type, designation, difficulty, round_category='NON_CODING', question_format='TEXT', programming_language='', count=5):
        from jobs.models import JobApplication
        application = JobApplication.objects.get(id=application_id)
        
        context = InterviewPromptService.build_config_context(application, round_type, designation, difficulty, round_category)
        
        # Get designation-specific focus (the #1 priority for question content)
        designation_focus = InterviewEngineService.DESIGNATION_FOCUS.get(designation, "")
        designation_instruction = ""
        if designation_focus:
            designation_instruction = (
                f"ROUND DESIGNATION FOCUS (HIGHEST PRIORITY):\n"
                f"This is a '{designation}' round. Questions MUST be about: {designation_focus}\n"
                f"The ROUND DESIGNATION is the #1 priority — it defines the topic area.\n"
                f"Do NOT let the job description's tech stack override the round designation.\n"
                f"For example: If designation is APTITUDE_ROUND, generate aptitude questions even if the job is for a Python Developer.\n\n"
            )

        # Build category-specific instructions (Coding vs Non-Coding)
        category_instruction = ""
        if round_category == 'CODING':
            lang_note = f" in {programming_language}" if programming_language else ""
            category_instruction = (
                f"ROUND TYPE: CODING — Generate hands-on coding/programming problems{lang_note}.\n"
                "CRITICAL RULES FOR CODING ROUNDS:\n"
                "- Questions MUST involve writing code, algorithms, data structures, debugging, or problem-solving.\n"
                "- Base questions on the JOB TITLE and REQUIRED SKILLS from the job description.\n"
                "- Do NOT analyze the candidate's resume. Focus ONLY on the role's technical requirements.\n"
                "- Include clear input/output specifications where applicable.\n"
                "- Test algorithmic thinking, code quality, optimization, and practical programming skills.\n"
                "- Do NOT generate theory-only, definition-based, or conceptual questions."
            )
        else:
            category_instruction = (
                "ROUND TYPE: NON-CODING — Generate theoretical, conceptual, or analytical questions.\n"
                "CRITICAL RULES FOR NON-CODING ROUNDS:\n"
                "- Questions should test understanding, knowledge, reasoning, and communication.\n"
                "- Do NOT generate questions that require writing code or programming.\n"
                "- Do NOT generate questions about specific programming languages or frameworks.\n"
                "- Focus STRICTLY on the round designation topic area described above."
            )

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
            f"Generate exactly {count} UNIQUE, DIVERSE, and NON-REPETITIVE interview questions for a '{designation}' round "
            f"at '{difficulty}' difficulty level.\n\n"
            f"CRITICAL DIVERSITY RULES:\n"
            f"- DO NOT repeat the same logic or theme across the pool.\n"
            f"- If generating Aptitude, avoid always starting with 'shopkeeper' profit/loss or basic number series. "
            f"Mix it up with Probability, Time & Work, Data Sufficiency, etc.\n"
            f"- Each of the {count} questions MUST cover a different sub-topic within the focus area.\n"
            f"- Ensure the questions are creative and professionally phrased.\n\n"
            f"{designation_instruction}"
            f"{category_instruction}\n\n"
            f"QUESTION FORMAT: {format_instruction}\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"IMPORTANT: For each question, provide an 'ideal_answer' or 'evaluation_criteria' that explains what a perfect answer should contain. "
            f"Return ONLY a JSON object with a single key 'questions' containing "
            f"an array of objects. Example:\n"
            f'{{"questions": [{{"question": "What is Python?", "ideal_answer": "Python is a high-level, interpreted language known for..."}}, ...]}}'
        )
        
        # Category-specific system prompts
        if round_category == 'CODING':
            system_prompt = (
                "You are an expert coding interview question generator. "
                "Generate programming problems and coding challenges based on the job title and required skills. "
                "Do NOT use the candidate's resume for coding rounds — focus purely on the role's technical requirements. "
                "Questions must be practical coding problems, NOT theoretical definitions. "
                "For each question, generate a detailed 'ideal_answer' showing the expected code solution or approach. "
                "Return ONLY valid JSON with the key 'questions' containing an array of objects with 'question' and 'ideal_answer' keys. "
                "No markdown, no extra text. DO NOT include unescaped newlines or tabs inside the JSON strings; use \\n and \\t instead."
            )
        else:
            system_prompt = (
                "You are an expert interview question generator. "
                "The MOST IMPORTANT rule: questions must STRICTLY match the round designation. "
                "If the round is APTITUDE, generate ONLY aptitude/numerical/logical questions — NOT programming questions. "
                "If the round is HR, generate ONLY HR questions. If Behavioral, ONLY behavioral. "
                "NEVER let the job's tech stack (Python, Java, etc.) influence non-technical rounds. "
                "For each question, also generate a detailed 'ideal_answer' for evaluation. "
                "Return ONLY valid JSON with the key 'questions' containing an array of objects with 'question' and 'ideal_answer' keys. "
                "No markdown, no extra text. DO NOT include unescaped newlines or tabs inside the JSON strings; use \\n and \\t instead."
            )
        
        logger.info(f"Generating {count} questions: designation={designation}, category={round_category}, format={question_format}")
        
        # Retry logic: attempt up to 2 times (AI can sometimes return malformed JSON)
        last_error = None
        for attempt in range(2):
            try:
                response_text = AIBaseService.generate_content(
                    prompt=prompt,
                    system_instruction=system_prompt,
                    temperature=0.8 if attempt > 0 else 0.9  # Higher temp for variety
                )
                
                if not response_text or not response_text.strip():
                    logger.warning(f"AI returned empty response (attempt {attempt + 1})")
                    last_error = ValueError("AI returned empty response")
                    continue
                
                logger.info(f"AI response (attempt {attempt + 1}, first 300 chars): {response_text[:300]}")
                
                cleaned_text = InterviewEngineService._clean_json_string(response_text)
                data = json.loads(cleaned_text)
                
                questions = data.get('questions', [])
                if not questions:
                    logger.warning(f"AI returned empty questions array (attempt {attempt + 1})")
                    last_error = ValueError("AI returned no questions")
                    continue
                
                return questions
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse failed (attempt {attempt + 1}): {e}\nRaw: {response_text[:500] if response_text else 'EMPTY'}")
                last_error = e
            except Exception as e:
                logger.error(f"Question generation failed (attempt {attempt + 1}): {e}")
                last_error = e
        
        raise ValueError(f"AI question generation failed after retries: {last_error}")
