import json
import logging
from AIrounds.models import InterviewSession, InterviewRound, InterviewQuestion
from AIrounds.services.ai_base import AIBaseService
from AIrounds.services.prompt_service import InterviewPromptService

logger = logging.getLogger("ai_rounds.reporter")

class InterviewReporter:
    """Generates comprehensive hiring reports and recommendations based on all completed rounds."""

    @staticmethod
    def generate_final_report(session_id):
        """
        Aggregates data from all rounds in a session and uses AI to produce a final hiring intelligence report.
        """
        try:
            session = InterviewSession.objects.get(id=session_id)
        except InterviewSession.DoesNotExist:
            logger.error(f"Session {session_id} not found for reporting.")
            raise ValueError("Session not found.")

        rounds = session.rounds.all().prefetch_related('questions')
        
        # 1. Aggregate technical data from all rounds
        aggregated_context = {
            "candidate": f"{session.candidate.first_name} {session.candidate.last_name}",
            "job_title": session.job_title,
            "rounds_data": []
        }

        for rnd in rounds:
            round_summary = {
                "round_type": rnd.round_type,
                "score": rnd.round_score,
                "evaluations": [
                    {
                        "question": q.question_text,
                        "answer": q.candidate_answer,
                        "ai_evaluation": q.evaluation
                    } for q in rnd.questions.all() if q.candidate_answer
                ]
            }
            aggregated_context["rounds_data"].append(round_summary)

        # 2. Construct specific final reporting prompt
        prompt = f"""
The candidate has completed all interview rounds. 
Synthesize all individual evaluations into a master hiring recommendation.
Analyze patterns across rounds (e.g., consistency, growth, logic depth).

INTERVIEW DATA:
{json.dumps(aggregated_context)}
"""

        system_instruction = InterviewPromptService.get_system_prompt() + """
---------------------------------------------------
FINAL SESSION REPORT RULES
---------------------------------------------------
1. Provide a balanced, senior-level assessment.
2. The overall_match_score (0-100) must reflect the average of round performances weighted by role relevance.
3. Be brutally honest about risk indicators.

OUTPUT FORMAT (JSON ONLY):
{
  "type": "FINAL_SESSION_REPORT",
  "overall_match_score": 0,
  "hiring_recommendation": "Strong Hire / Hire / No Hire / Keep in Pipeline",
  "technical_assessment": "",
  "communication_assessment": "",
  "coding_assessment": "",
  "cultural_fit": "",
  "strengths": [],
  "weaknesses": [],
  "risk_indicators": [],
  "ranking_justification": ""
}
"""

        # 3. Call AI for synthesis
        response_text = AIBaseService.generate_content(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=0.3 # High precision for final report
        )
        
        try:
            report_data = json.loads(response_text)
            
            # Persist the final summary to the session
            session.summary = report_data
            session.overall_score = report_data.get('overall_match_score', 0)
            session.status = 'COMPLETED'
            session.save()
            
            logger.info(f"Generated final hiring report for session {session.id}")
            return report_data
        except Exception as e:
            logger.error(f"Failed to parse AI final report: {e}")
            raise ValueError("AI failed to synthesize the final report.")
