from datetime import timedelta
from django.utils import timezone
from AIrounds.models import InterviewSession, InterviewRound, InterviewQuestion
from jobs.models import JobApplication
import logging

logger = logging.getLogger("ai_rounds.orchestrator")

class InterviewOrchestrator:
    """Orchestrates the creation and configuration of interview processes."""

    @staticmethod
    def create_interview_from_config(application_id, overall_config, rounds_config):
        """
        Initializes an interview session and its constituent rounds based on recruiter settings.
        """
        try:
            application = JobApplication.objects.get(id=application_id)
        except JobApplication.DoesNotExist:
            logger.error(f"JobApplication {application_id} not found for orchestration.")
            raise ValueError("Job Application not found.")

        # 1. Prepare Session Metadata
        expires_at = timezone.now() + timedelta(days=overall_config.get('expires_in_days', 7))
        
        session = InterviewSession.objects.create(
            candidate=application.applicant,
            application=application,
            job_title=application.job.title,
            job_description=application.job.description,
            resume_data=application.ai_analysis if application.ai_analysis else None,
            config=overall_config,
            expires_at=expires_at,
            status='PENDING'
        )

        # 2. Bulk Create Configured Rounds
        rounds = []
        for r_cfg in rounds_config:
            rnd = InterviewRound.objects.create(
                session=session,
                strategy_tier=r_cfg.get('type', 'TECHNICAL'),
                designation=r_cfg.get('title', 'TECHNICAL_SCREENING'),
                difficulty=r_cfg.get('difficulty', 'MID'),
                timer_seconds=r_cfg.get('timer_seconds') or r_cfg.get('timer', 0),
                max_questions=r_cfg.get('max_questions', 10),
                settings=r_cfg.get('settings', {}),
                status='PENDING'
            )
            rounds.append(rnd)

            # 3. Handle pre-configured questions if provided
            pre_questions = r_cfg.get('questions', [])
            total_marks = 0
            for q_data in pre_questions:
                if isinstance(q_data, dict):
                    q_text = q_data.get('text', '')
                    q_marks = int(q_data.get('marks', 10))
                else:
                    q_text = str(q_data)
                    q_marks = 10
                
                if q_text.strip():
                    InterviewQuestion.objects.create(
                        round=rnd,
                        question_text=q_text,
                        marks=q_marks
                    )
                    total_marks += q_marks
                    
            rnd.total_marks = total_marks
            rnd.save()

        logger.info(f"Orchestrated interview session {session.id} with {len(rounds)} rounds for {application.applicant.email}")
        return session, rounds

    @staticmethod
    def auto_orchestrate(application):
        """
        Automatically orchestrates an interview based on the application and job data.
        Triggered when application status changes to 'INTERVIEW'.
        """
        # 0. Check for existing session to prevent duplication
        existing_session = InterviewSession.objects.filter(application=application).first()
        if existing_session:
            logger.info(f"Auto-orchestration skipped: Session already exists for App: {application.id}")
            return existing_session

        # 1. Prepare default overall config
        overall_config = {
            'expires_in_days': 7,
            'auto_generated': True,
            'source': 'ATS_AUTO_MOVE'
        }
        
        # 2. Define default rounds based on job (Can be expanded with AI suggestions later)
        # Use both strategy tier and designation for maximum context
        rounds_config = [
            {
                'type': 'TECHNICAL',
                'title': 'TECHNICAL_SCREENING',
                'difficulty': 'MID',
                'timer': 1800, # 30 mins
                'max_questions': 5,
                'settings': {'focus': 'Core Competencies'}
            },
            {
                'type': 'BEHAVIORAL',
                'title': 'BEHAVIORAL_ROUND',
                'difficulty': 'MID',
                'timer': 1200, # 20 mins
                'max_questions': 3,
                'settings': {'focus': 'Culture Fit'}
            }
        ]
        
        # 3. Create session
        expires_at = timezone.now() + timedelta(days=7)
        
        session = InterviewSession.objects.create(
            candidate=application.applicant,
            application=application,
            job_title=application.job.title,
            job_description=application.job.description,
            resume_data=application.ai_analysis if application.ai_analysis else None,
            # Pass the ATS screening score as the initial baseline
            overall_score=application.ai_score if application.ai_score else 0,
            config=overall_config,
            expires_at=expires_at,
            status='PENDING'
        )
        
        # 4. Create rounds
        for r_cfg in rounds_config:
            InterviewRound.objects.create(
                session=session,
                round_type=r_cfg['type'],
                difficulty=r_cfg['difficulty'],
                timer_seconds=r_cfg['timer'],
                max_questions=r_cfg['max_questions'],
                settings=r_cfg['settings'],
                status='PENDING'
            )
            
        logger.info(f"Auto-orchestrated interview for {application.applicant.email} (App: {application.id})")
        return session

    @staticmethod
    def get_session_by_token(token):
        """Retrieves and validates an active interview session via its invite token."""
        try:
            session = InterviewSession.objects.get(invite_token=token)
            
            # Check expiration
            if session.expires_at and session.expires_at < timezone.now():
                logger.warning(f"Attempted access to expired session token: {token}")
                return None, "Interview link has expired."
            
            if session.status == 'CANCELLED':
                return None, "This interview session has been cancelled."
                
            return session, None
        except InterviewSession.DoesNotExist:
            return None, "Invalid interview link."
