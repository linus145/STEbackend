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
        logger.info(f"Starting Celery voice transcript split task for question {question_id}...")
        pairs = AIInterviewService.split_voice_transcript(answer)
        AIInterviewService.save_split_transcript(question_id, pairs)
        logger.info(f"Successfully split and saved transcript for question {question_id}.")
        return f"Successfully split transcript for question {question_id}."
    except Exception as e:
        logger.error(f"Error in task_split_and_save_voice_transcript: {e}")
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
        raise e
