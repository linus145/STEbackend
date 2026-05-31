import logging
from celery import shared_task
from AIrounds.models import InterviewRound, InterviewQuestion, InterviewSession
from AIrounds.services.engine_service import InterviewEngineService
from AIrounds.services.evaluation import InterviewEvaluationService

logger = logging.getLogger("ai_rounds.tasks")

@shared_task
def task_generate_question_pool(application_id, round_type, designation, difficulty, round_category, question_format, programming_language, count, coding_topics=None, coding_frameworks=None):
    """
    Celery task to generate a pool of interview questions.
    """
    try:
        questions = InterviewEngineService.generate_question_pool(
            application_id, round_type, designation, difficulty, round_category, question_format, programming_language, count, coding_topics, coding_frameworks
        )
        return questions
    except Exception as e:
        logger.error(f"Error in task_generate_question_pool: {e}")
        try:
            from AIrounds.models import InterviewSession
            session = InterviewSession.objects.filter(application_id=application_id).order_by('-created_at').first()
            if session:
                session.status = 'FAILED'
                session.save(update_fields=['status'])
        except Exception as ex:
            logger.error(f"Failed to transition session to FAILED in task_generate_question_pool: {ex}")
        raise e

@shared_task
def task_regenerate_round_questions(round_id, count):
    """
    Celery task to regenerate questions for a specific round.
    """
    try:
        rnd = InterviewRound.objects.select_related('session__application').get(id=round_id)
        application_id = str(rnd.session.application.id)

        coding_topics = rnd.settings.get('coding_topics') if isinstance(rnd.settings, dict) else None
        coding_frameworks = rnd.settings.get('coding_frameworks') if isinstance(rnd.settings, dict) else None

        questions = InterviewEngineService.generate_question_pool(
            application_id,
            rnd.round_type or rnd.designation,
            rnd.designation,
            rnd.difficulty,
            rnd.round_category or 'NON_CODING',
            rnd.question_format or 'TEXT',
            rnd.programming_language or '',
            count,
            coding_topics,
            coding_frameworks
        )

        # Delete old questions and create new ones
        rnd.questions.all().delete()
        for q_data in questions:
            if isinstance(q_data, dict):
                q_text = q_data.get('question')
                q_ideal = q_data.get('ideal_answer')
                q_mcq = q_data.get('mcq_options')
            else:
                q_text = q_data
                q_ideal = None
                q_mcq = None

            InterviewQuestion.objects.create(
                round=rnd,
                question_text=q_text,
                ideal_answer=q_ideal,
                question_type=rnd.question_format or 'TEXT',
                mcq_options=q_mcq,
            )
        
        return f"{len(questions)} questions regenerated for round {round_id}"
    except Exception as e:
        logger.error(f"Error in task_regenerate_round_questions: {e}")
        try:
            from AIrounds.models import InterviewRound
            rnd = InterviewRound.objects.select_related('session').get(id=round_id)
            if rnd.session:
                rnd.session.status = 'FAILED'
                rnd.session.save(update_fields=['status'])
        except Exception as ex:
            logger.error(f"Failed to transition session to FAILED in task_regenerate_round_questions: {ex}")
        raise e

@shared_task
def task_evaluate_answer(session_id, round_id, question_id, answer_text):
    """
    Celery task to evaluate a candidate's answer using AI.
    """
    try:
        eval_data = InterviewEvaluationService.evaluate_answer(
            session_id, round_id, question_id, answer_text
        )
        return eval_data
    except Exception as e:
        logger.error(f"Error in task_evaluate_answer: {e}")
        try:
            from AIrounds.models import InterviewSession
            session = InterviewSession.objects.get(id=session_id)
            session.status = 'FAILED'
            session.save(update_fields=['status'])
        except Exception as ex:
            logger.error(f"Failed to transition session to FAILED in task_evaluate_answer: {ex}")
        raise e

@shared_task
def task_send_interview_invite(session_id):
    """
    Celery task to send an interview invitation email in the background.
    """
    try:
        from AIrounds.models import InterviewSession
        from AIrounds.services.notifier import InterviewNotifier
        session = InterviewSession.objects.select_related('candidate').get(id=session_id)
        success = InterviewNotifier.send_invite_email_sync(session)
        return f"Invite email task completed. Success: {success}"
    except Exception as e:
        logger.error(f"Error in task_send_interview_invite for session {session_id}: {e}")
        try:
            from AIrounds.models import InterviewSession
            session = InterviewSession.objects.get(id=session_id)
            session.status = 'FAILED'
            session.save(update_fields=['status'])
        except Exception as ex:
            logger.error(f"Failed to transition session to FAILED in task_send_interview_invite: {ex}")
        raise e
