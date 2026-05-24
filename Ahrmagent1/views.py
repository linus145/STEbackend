from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
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
    API View to get details of a specific execution, update it or delete it.
    """
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            execution = AgentExecution.objects.get(pk=pk)
            serializer = AgentExecutionSerializer(execution)
            return Response(serializer.data)
        except AgentExecution.DoesNotExist:
            return Response({"error": "Execution not found"}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        try:
            execution = AgentExecution.objects.get(pk=pk)
            serializer = AgentExecutionSerializer(execution, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except AgentExecution.DoesNotExist:
            return Response({"error": "Execution not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        try:
            execution = AgentExecution.objects.get(pk=pk)
            execution.delete()
            return Response({"status": "success", "message": "Execution deleted successfully."}, status=status.HTTP_200_OK)
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
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Plan-aware capability guard in the backend
        try:
            from subscription.models import UserSubscription
            user_sub = UserSubscription.objects.get(user=request.user)
            if user_sub.status != "active" or not user_sub.plan or user_sub.plan.price < 18000:
                return Response(
                    {
                        "action_type": "wait",
                        "wait_after_ms": 5000,
                        "thinking": "Enterprise AI OS plan required to run autonomous agent.",
                        "description": "Subscription verification failed. Act mode locked.",
                        "error": "Insufficient permissions. Enterprise plan required.",
                    },
                    status=status.HTTP_403_FORBIDDEN
                )
        except Exception:
            return Response(
                {
                    "action_type": "wait",
                    "wait_after_ms": 5000,
                    "thinking": "No active subscription found. Enterprise plan required.",
                    "description": "Subscription verification failed.",
                    "error": "No active subscription. Enterprise plan required.",
                },
                status=status.HTTP_403_FORBIDDEN
            )

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


from Ahrmagent1.models import AgentChatHistory
from Ahrmagent1.serializers import AgentChatHistorySerializer

class AgentExecutionListView(APIView):
    """
    API View to get all historical agent executions (Autonomous mode history).
    """
    permission_classes = [AllowAny]

    def get(self, request):
        executions = AgentExecution.objects.all().order_by('-started_at')
        serializer = AgentExecutionSerializer(executions, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = AgentExecutionSerializer(data=request.data)
        if serializer.is_valid():
            execution = serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AgentChatHistoryView(APIView):
    """
    API View to retrieve and save conversational AI chat history (Conversational mode history).
    """
    def get(self, request):
        if request.user.is_authenticated:
            chats = AgentChatHistory.objects.filter(user=request.user).order_by('timestamp')
        else:
            chats = AgentChatHistory.objects.all().order_by('timestamp')
        serializer = AgentChatHistorySerializer(chats, many=True)
        return Response(serializer.data)

    def post(self, request):
        sender = request.data.get('sender')
        text = request.data.get('text')
        
        if not sender or not text:
            return Response({"error": "sender and text are required"}, status=status.HTTP_400_BAD_REQUEST)
            
        chat = AgentChatHistory.objects.create(
            user=request.user if request.user.is_authenticated else None,
            sender=sender,
            text=text
        )
        serializer = AgentChatHistorySerializer(chat)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AgentChatHistoryClearView(APIView):
    """
    API View to clear conversational AI chat history.
    """
    def delete(self, request):
        if request.user.is_authenticated:
            AgentChatHistory.objects.filter(user=request.user).delete()
        else:
            AgentChatHistory.objects.all().delete()
        return Response({"status": "success", "message": "Chat history cleared."})
