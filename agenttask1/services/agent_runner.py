import logging
from typing import Dict, Any, Optional

from agenttask1.core.graph import agent_task_pipeline, AgentTaskState
from startups.models import Startup

logger = logging.getLogger(__name__)


class AgentTaskExecutionService:
    """
    Orchestration service to run deterministic LangGraph automation tasks.
    Zero external AI or LLM APIs required.
    """

    @classmethod
    def resolve_startup(cls, user, startup_id: Optional[str] = None):
        """Resolves the active startup tenant for execution."""
        if startup_id:
            try:
                st = Startup.objects.filter(id=startup_id).first()
                if st:
                    return st
            except Exception:
                pass

        if user and not user.is_anonymous:
            try:
                # 1. Use the proven helper from payroll.views
                from payroll.views import get_active_startup
                class FakeRequest:
                    def __init__(self, u):
                        self.user = u
                st = get_active_startup(FakeRequest(user))
                if st:
                    return st
            except Exception as e:
                logger.warning(f"Failed resolving via get_active_startup: {e}")

            # 2. Check direct user startups relation or founder
            try:
                if hasattr(user, 'startups'):
                    st = user.startups.first()
                    if st:
                        return st
            except Exception:
                pass

            try:
                st = Startup.objects.filter(founder=user).first()
                if st:
                    return st
            except Exception:
                pass

        # Fallback to first startup in system
        try:
            return Startup.objects.first()
        except Exception:
            return None

    @classmethod
    def execute_task(
        cls,
        user_input: str,
        user=None,
        startup_id: Optional[str] = None,
        month: Optional[int] = None,
        year: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executes the LangGraph automation pipeline for the user input.
        """
        startup = cls.resolve_startup(user, startup_id)

        initial_state: AgentTaskState = {
            "user_input": user_input or "",
            "tool_id": None,
            "month": month,
            "year": year,
            "startup": startup,
            "is_valid": False,
            "error_message": None,
            "execution_result": {},
            "summary": "",
            "audit_logs": [],
            "status": "INITIATED"
        }

        try:
            final_state = agent_task_pipeline.invoke(initial_state)
            
            return {
                "status": final_state.get("status"),
                "tool_activated": final_state.get("tool_id"),
                "parameters": {
                    "month": final_state.get("month"),
                    "year": final_state.get("year"),
                    "startup_id": str(startup.id) if startup else None
                },
                "summary": final_state.get("summary"),
                "audit_logs": final_state.get("audit_logs", []),
                "data": final_state.get("execution_result", {})
            }
        except Exception as e:
            logger.error(f"Error during agent task execution: {e}")
            return {
                "status": "FAILED",
                "tool_activated": None,
                "parameters": {"month": month, "year": year},
                "summary": f"System error during automation run: {str(e)}",
                "audit_logs": [f"[ERROR] Execution failed: {str(e)}"],
                "data": {}
            }
