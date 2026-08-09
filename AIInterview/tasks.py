import logging
from celery import shared_task
from AIInterview.services import AIInterviewService

logger = logging.getLogger("ai_interview.tasks")

@shared_task
def task_split_and_save_voice_transcript(question_id, answer):
    """
    Celery task to offload dynamic voice dialogue splitting and DB record creation in the background.
    """
    try:
        from AIrounds.models import InterviewQuestion
        from AIrounds.services.ai_base import AIBaseService
        q = InterviewQuestion.objects.select_related('round__session__application__job').get(id=question_id)
        company = q.round.session.application.job.company if (q.round.session.application and q.round.session.application.job) else None
        model_name = AIBaseService.get_model_for_company(company)

        logger.info(f"Starting Celery voice transcript split task for question {question_id}...")
        pairs = AIInterviewService.split_voice_transcript(answer, model_name=model_name)
        AIInterviewService.save_split_transcript(question_id, pairs)
        logger.info(f"Successfully split and saved transcript for question {question_id}.")
        return f"Successfully split transcript for question {question_id}."
    except Exception as e:
        logger.error(f"Error in task_split_and_save_voice_transcript: {e}")
        try:
            from AIrounds.models import InterviewQuestion
            q = InterviewQuestion.objects.select_related('round__session').get(id=question_id)
            if q.round and q.round.session:
                q.round.session.status = 'FAILED'
                q.round.session.save(update_fields=['status'])
        except Exception as ex:
            logger.error(f"Failed to transition session to FAILED in task_split_and_save_voice_transcript: {ex}")
        raise e

@shared_task
def task_evaluate_voice_question(question_id):
    """
    Celery task to evaluate typing/spoken questions in the background using Gemini.
    """
    try:
        logger.info(f"Starting Celery AI evaluation task for question {question_id}...")
        eval_data = AIInterviewService.evaluate_question_logic(question_id)
        logger.info(f"Successfully evaluated question {question_id}.")
        return eval_data
    except Exception as e:
        logger.error(f"Error in task_evaluate_voice_question: {e}")
        try:
            from AIrounds.models import InterviewQuestion
            q = InterviewQuestion.objects.select_related('round__session').get(id=question_id)
            if q.round and q.round.session:
                q.round.session.status = 'FAILED'
                q.round.session.save(update_fields=['status'])
        except Exception as ex:
            logger.error(f"Failed to transition session to FAILED in task_evaluate_voice_question: {ex}")
        raise e
