import logging
import asyncio
import time
from celery import shared_task
from django.utils import timezone
from Ahrmagent1.models import AgentExecution
from Ahrmagent1.services.recruitment_agent import RecruitmentAgentService

logger = logging.getLogger("ahrmagent1.tasks")

@shared_task
def task_run_recruitment_agent(job_data, handover, execution_id):
    """
    Celery task to run recruitment agent workflows.
    """
    start_time = time.time()
    try:
        agent = RecruitmentAgentService(execution_id=execution_id)
        
        # We need an event loop for the async workflow methods
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            workflow = agent.handover_workflow(job_data) if handover else agent.create_job_workflow(job_data)
            loop.run_until_complete(workflow)
            
            execution = AgentExecution.objects.get(id=execution_id)
            execution.status = 'success'
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            execution = AgentExecution.objects.get(id=execution_id)
            execution.status = 'failed'
            execution.metadata['error'] = str(e)
        finally:
            loop.close()
            
        execution.completed_at = timezone.now()
        execution.execution_time = time.time() - start_time
        execution.save()
        
    except Exception as e:
        logger.error(f"Critical error in task_run_recruitment_agent: {e}")
        try:
            execution = AgentExecution.objects.get(id=execution_id)
            execution.status = 'failed'
            execution.metadata['error'] = str(e)
            execution.save()
        except:
            pass

@shared_task
def task_run_hiring_workflow(job_id, target_count, recruiter_user_id, execution_id):
    """
    Celery task to run the full hiring workflow.
    """
    start_time = time.time()
    try:
        agent = RecruitmentAgentService(execution_id=execution_id)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(
                agent.execute_full_hiring_workflow(
                    job_id, target_count, 
                    use_existing=True, 
                    recruiter_user_id=recruiter_user_id
                )
            )
            
            execution = AgentExecution.objects.get(id=execution_id)
            execution.status = 'success'
        except Exception as e:
            logger.error(f"Hiring workflow failed: {e}")
            execution = AgentExecution.objects.get(id=execution_id)
            execution.status = 'failed'
            execution.metadata['error'] = str(e)
        finally:
            loop.close()
            
        execution.completed_at = timezone.now()
        execution.execution_time = time.time() - start_time
        execution.save()
        
    except Exception as e:
        logger.error(f"Critical error in task_run_hiring_workflow: {e}")
        try:
            execution = AgentExecution.objects.get(id=execution_id)
            execution.status = 'failed'
            execution.metadata['error'] = str(e)
            execution.save()
        except:
            pass
