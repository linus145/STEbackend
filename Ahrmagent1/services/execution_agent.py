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
            agent_type='recruitment_agent_handover' if handover else 'recruitment_agent',
            status='running',
            metadata={'job_data': job_data, 'handover': handover}
        )
        
        start_time = time.time()
        
        try:
            # 2. Run Workflow
            agent = RecruitmentAgentService(execution_id=execution.id)
            
            new_loop = False
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                new_loop = True
            
            workflow = agent.handover_workflow(job_data) if handover else agent.create_job_workflow(job_data)
            
            if not loop.is_running():
                loop.run_until_complete(workflow)
                if new_loop:
                    loop.close()
            else:
                asyncio.create_task(workflow)
            
            # 3. Update Success
            execution.status = 'success'
            
        except Exception as e:
            execution.status = 'failed'
            execution.metadata['error'] = str(e)
            
        finally:
            execution.completed_at = timezone.now()
            execution.execution_time = time.time() - start_time
            execution.save()
            
        return execution

    @staticmethod
    def run_hiring_workflow(workflow_data, recruiter_user_id=None):
        # 1. Initialize DB Record
        execution = AgentExecution.objects.create(
            agent_type='full_hiring_workflow',
            status='running',
            metadata={'workflow_data': workflow_data}
        )
        
        job_id = workflow_data.get('job_id')
        target_count = workflow_data.get('target_count', 5)
        execution_id = str(execution.id)

        # 2. Run workflow in a dedicated background thread with its own event loop
        # This prevents corrupting Django's ASGI thread executor
        def _run_in_background(exec_id, j_id, t_count, r_user_id):
            # Close inherited DB connection — each thread needs its own
            connection.close()
            
            start_time = time.time()
            try:
                connection.ensure_connection()
                
                agent = RecruitmentAgentService(execution_id=exec_id)
                
                # Create a fresh event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    loop.run_until_complete(
                        agent.execute_full_hiring_workflow(
                            j_id, t_count, 
                            use_existing=True, 
                            recruiter_user_id=r_user_id
                        )
                    )
                    
                    connection.ensure_connection()
                    exec_obj = AgentExecution.objects.get(id=exec_id)
                    exec_obj.status = 'success'
                    exec_obj.completed_at = timezone.now()
                    exec_obj.execution_time = time.time() - start_time
                    exec_obj.save()
                    
                except Exception as e:
                    connection.ensure_connection()
                    exec_obj = AgentExecution.objects.get(id=exec_id)
                    exec_obj.status = 'failed'
                    exec_obj.metadata['error'] = str(e)
                    exec_obj.completed_at = timezone.now()
                    exec_obj.execution_time = time.time() - start_time
                    exec_obj.save()
                finally:
                    loop.close()
            except Exception as e:
                print(f"[ExecutionAgent] Background thread critical error: {e}")
            finally:
                connection.close()

        thread = threading.Thread(
            target=_run_in_background,
            args=(execution_id, job_id, target_count, recruiter_user_id),
            daemon=True
        )
        thread.start()
        
        # Return immediately — workflow runs in background
        return execution

