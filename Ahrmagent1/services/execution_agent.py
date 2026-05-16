from Ahrmagent1.models import AgentExecution
from Ahrmagent1.services.recruitment_agent import RecruitmentAgentService
from django.utils import timezone
from django.db import connection
import asyncio
import threading
import time


class ExecutionAgentService:
    """
    Orchestrator for agent execution.
    Manages database state and triggers specific agent workflows.
    """

    @staticmethod
    def run_recruitment_agent(job_data, handover=False):
        # 1. Initialize DB Record
        execution = AgentExecution.objects.create(
            agent_type="recruitment_agent_handover"
            if handover
            else "recruitment_agent",
            status="running",
            metadata={"job_data": job_data, "handover": handover},
        )

        # 2. Trigger Celery Task
        from Ahrmagent1.tasks import task_run_recruitment_agent

        task_run_recruitment_agent.delay(job_data, handover, str(execution.id))

        return execution

    @staticmethod
    def run_hiring_workflow(workflow_data, recruiter_user_id=None):
        # 1. Initialize DB Record
        execution = AgentExecution.objects.create(
            agent_type="full_hiring_workflow",
            status="running",
            metadata={"workflow_data": workflow_data},
        )

        job_id = workflow_data.get("job_id")
        target_count = workflow_data.get("target_count", 5)

        # 2. Trigger Celery Task
        from Ahrmagent1.tasks import task_run_hiring_workflow

        task_run_hiring_workflow.delay(
            job_id, target_count, recruiter_user_id, str(execution.id)
        )

        # Return immediately — workflow runs in Celery background
        return execution
