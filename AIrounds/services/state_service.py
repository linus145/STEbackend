from ..models import InterviewSession, InterviewRound

class InterviewStateService:
    """Manages the creation and state of interview sessions and rounds."""
    
    @staticmethod
    def start_session(candidate, job_title, job_description, resume_data=None, skills=None, experience=None):
        return InterviewSession.objects.create(
            candidate=candidate,
            job_title=job_title,
            job_description=job_description,
            resume_data=resume_data,
            candidate_skills=skills,
            candidate_experience=experience,
            status='ACTIVE'
        )

    @staticmethod
    def add_round(session_id, round_type, difficulty='MEDIUM'):
        session = InterviewSession.objects.get(id=session_id)
        return InterviewRound.objects.create(
            session=session,
            round_type=round_type,
            difficulty=difficulty,
            status='ACTIVE'
        )
