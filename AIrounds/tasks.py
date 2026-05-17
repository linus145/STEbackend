import logging
from celery import shared_task
from AIrounds.models import InterviewRound, InterviewQuestion, InterviewSession
from AIrounds.services.engine_service import InterviewEngineService

logger = logging.getLogger("ai_rounds.tasks")

@shared_task
def task_generate_question_pool(application_id, round_type, designation, difficulty, round_category, question_format, programming_language, count):
    """
    Celery task to generate a pool of interview questions.
    """
    try:
        questions = InterviewEngineService.generate_question_pool(
            application_id, round_type, designation, difficulty, round_category, question_format, programming_language, count
        )
        return questions
    except Exception as e:
        logger.error(f"Error in task_generate_question_pool: {e}")
        raise e

@shared_task
def task_regenerate_round_questions(round_id, count):
    """
    Celery task to regenerate questions for a specific round.
    """
    try:
        rnd = InterviewRound.objects.select_related('session__application').get(id=round_id)
        application_id = str(rnd.session.application.id)

        questions = InterviewEngineService.generate_question_pool(
            application_id,
            rnd.round_type or rnd.designation,
            rnd.designation,
            rnd.difficulty,
            rnd.round_category or 'NON_CODING',
            rnd.question_format or 'TEXT',
            rnd.programming_language or '',
            count
        )

        # Delete old questions and create new ones
        rnd.questions.all().delete()
        for q_data in questions:
            if isinstance(q_data, dict):
                q_text = q_data.get('question')
                q_ideal = q_data.get('ideal_answer')
            else:
                q_text = q_data
                q_ideal = None

            InterviewQuestion.objects.create(
                round=rnd,
                question_text=q_text,
                ideal_answer=q_ideal,
                question_type=rnd.question_format or 'TEXT',
            )
        
        return f"{len(questions)} questions regenerated for round {round_id}"
    except Exception as e:
        logger.error(f"Error in task_regenerate_round_questions: {e}")
        raise e

@shared_task
def task_evaluate_answer(session_id, round_id, question_id, answer_text):
    """
    Celery task to evaluate a candidate's answer using AI.
    """
    try:
        eval_data = InterviewEngineService.evaluate_answer(
            session_id, round_id, question_id, answer_text
        )
        return eval_data
    except Exception as e:
        logger.error(f"Error in task_evaluate_answer: {e}")
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
        raise e
