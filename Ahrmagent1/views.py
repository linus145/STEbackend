from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from Ahrmagent1.serializers import AgentRunRequestSerializer, AgentExecutionSerializer
from Ahrmagent1.services.execution_agent import ExecutionAgentService
from Ahrmagent1.services.autonomous_agent import AutonomousAgentService
from Ahrmagent1.models import AgentExecution


class AgentRunView(APIView):
    """
    API View to trigger a recruitment agent execution.
    """
    def post(self, request):
        serializer = AgentRunRequestSerializer(data=request.data)
        if serializer.is_valid():
            task_type = serializer.validated_data.get('task_type')
            
            if task_type == 'full_hiring_workflow':
                execution = ExecutionAgentService.run_hiring_workflow(
                    serializer.validated_data,
                    recruiter_user_id=request.user.id if request.user.is_authenticated else None
                )
            else:
                handover = serializer.validated_data.get('handover', False)
                execution = ExecutionAgentService.run_recruitment_agent(
                    serializer.validated_data, 
                    handover=handover
                )
            
            response_serializer = AgentExecutionSerializer(execution)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AgentExecutionDetailView(APIView):
    """
    API View to get details of a specific execution.
    """
    def get(self, request, pk):
        try:
            execution = AgentExecution.objects.get(pk=pk)
            serializer = AgentExecutionSerializer(execution)
            return Response(serializer.data)
        except AgentExecution.DoesNotExist:
            return Response({"error": "Execution not found"}, status=status.HTTP_404_NOT_FOUND)

class AgentPlanView(APIView):
    """
    API View to generate an execution plan for a goal.
    (Legacy — hardcoded keyword-based planning)
    """
    permission_classes = [AllowAny]

    def post(self, request):
        goal_data = request.data
        plan = AutonomousAgentService.generate_plan(goal_data)
        return Response({"plan": plan}, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────
# LLM-Powered Agent — Observe → Think → Act (in-browser)
# ─────────────────────────────────────────────────────────────────

class LLMThinkView(APIView):
    """
    The brain of the autonomous agent.
    
    Frontend sends current page state → this endpoint sends it to Gemini →
    returns the next action to execute.
    
    The frontend runs the observe→think→act loop:
      1. Frontend captures DOM state (visible elements, texts, buttons)
      2. POST /autonomousagent1/llm/think/ with {goal, page_state, history}
      3. This view sends everything to Gemini with app knowledge
      4. Returns the next action: {action_type, selector, value, ...}
      5. Frontend executes the action via AgentExecutor
      6. Loop back to step 1
    """
    permission_classes = [AllowAny]

    def post(self, request):
        goal = request.data.get("goal", "")
        page_state = request.data.get("page_state", {})
        action_history = request.data.get("action_history", [])
        iteration = request.data.get("iteration", 1)
        user_response = request.data.get("user_response", None)
        original_goal = request.data.get("original_goal", None)

        if not goal:
            return Response(
                {"error": "Goal is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from Ahrmagent1.services.llm_planner import get_planner

            planner = get_planner()
            action = planner.think(
                goal=goal,
                page_state=page_state,
                action_history=action_history,
                iteration=iteration,
                user_response=user_response,
                original_goal=original_goal,
            )

            return Response(action, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {
                    "action_type": "wait",
                    "wait_after_ms": 3000,
                    "thinking": f"Server error: {str(e)}",
                    "description": "Backend error, retrying...",
                    "error": str(e),
                },
                status=status.HTTP_200_OK  # Still return 200 so the agent loop doesn't crash
            )
