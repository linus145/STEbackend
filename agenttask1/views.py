from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from agenttask1.services.agent_runner import AgentTaskExecutionService
from agenttask1.tools.intent_extractor import detect_tool_intent, AVAILABLE_TOOLS_REGISTRY


class ExecuteAgentTaskView(APIView):
    """
    Executes a deterministic LangGraph agent task based on natural language input
    or structured parameters without any LLM API calls.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        user_input = request.data.get("query") or request.data.get("goal") or request.data.get("input") or ""
        startup_id = request.data.get("startup_id")
        month = request.data.get("month")
        year = request.data.get("year")

        # Convert month/year to int if passed explicitly in JSON
        try:
            month = int(month) if month is not None else None
        except (ValueError, TypeError):
            month = None

        try:
            year = int(year) if year is not None else None
        except (ValueError, TypeError):
            year = None

        result = AgentTaskExecutionService.execute_task(
            user_input=user_input,
            user=request.user,
            startup_id=startup_id,
            month=month,
            year=year
        )

        # Return 200 OK with structured result so frontend receives full audit logs and failure guidance
        return Response(result, status=status.HTTP_200_OK)


class ParseIntentView(APIView):
    """
    Dry-run endpoint to preview the detected tool and extracted parameters
    from a user query without triggering tool execution.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        user_input = request.data.get("query") or request.data.get("goal") or request.data.get("input") or ""
        parsed = detect_tool_intent(user_input)
        return Response(parsed, status=status.HTTP_200_OK)


class ListAvailableToolsView(APIView):
    """
    Returns the registry of available deterministic tools and schemas.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({
            "tools": AVAILABLE_TOOLS_REGISTRY,
            "count": len(AVAILABLE_TOOLS_REGISTRY)
        }, status=status.HTTP_200_OK)
