import json
import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from google import genai
from google.genai import types
from jobs.models import JobPost, Skill
from startups.models import CompanyProfile
from AIAgents.models import AISearchHistory
from useraccounts.models import CustomUser
from django.db.models import Q
import os

logger = logging.getLogger("ai_agents.tasks")

@shared_task
def task_execute_job_post(company_id, prompt):
    """
    Celery task to generate and post a job using AI.
    """
    try:
        from AIAgents.services import AIAgentService
        company = CompanyProfile.objects.get(id=company_id)
        job = AIAgentService.execute_job_post(company, prompt)
        return {"job_id": str(job.id), "title": job.title}
    except Exception as e:
        logger.error(f"Error in task_execute_job_post: {e}")
        raise e

@shared_task
def task_execute_talent_search(prompt, user_id):
    """
    Celery task to search for talent using AI.
    """
    try:
        from AIAgents.services import AIAgentService
        user = CustomUser.objects.get(id=user_id)
        results = AIAgentService.execute_talent_search(prompt, user)
        return results
    except Exception as e:
        logger.error(f"Error in task_execute_talent_search: {e}")
        raise e
