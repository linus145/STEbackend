from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from Ahrmagent1.serializers import AgentRunRequestSerializer, AgentExecutionSerializer
from Ahrmagent1.services.execution_agent import ExecutionAgentService
from Ahrmagent1.services.autonomous_agent import AutonomousAgentService
from Ahrmagent1.models import AgentExecution
from creditsystem.utils import burn_credits


class AgentRunView(APIView):
    """
    API View to trigger a recruitment agent execution.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AgentRunRequestSerializer(data=request.data)
        if serializer.is_valid():
            task_type = serializer.validated_data.get('task_type')
            
            # Check and burn credits
            job_id = serializer.validated_data.get('job_id')
            if task_type == 'full_hiring_workflow':
                burn_credits(
                    request.user, 
                    150, 
                    "Executed full hiring workflow autonomous agent.",
                    module="autonomous_agent",
                    job_id=str(job_id) if job_id else None,
                    action_type="full_hiring_workflow"
                )
                execution = ExecutionAgentService.run_hiring_workflow(
                    serializer.validated_data,
                    recruiter_user_id=request.user.id if request.user.is_authenticated else None
                )
            else:
                handover = serializer.validated_data.get('handover', False)
                desc = "Executed recruitment agent (handover mode)." if handover else "Executed recruitment agent."
                action_name = "recruitment_agent_handover" if handover else "recruitment_agent"
                burn_credits(
                    request.user, 
                    10, 
                    desc,
                    module="autonomous_agent",
                    job_id=str(job_id) if job_id else None,
                    action_type=action_name
                )
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
        plan = AutonomousAgentService.generate_plan(goal_data, user=request.user)
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

        # Burn credits for autonomous think step
        goal = request.data.get("goal", "")
        iteration = request.data.get("iteration", 1)
        try:
            burn_credits(
                request.user, 
                0.1, 
                f"Autonomous Agent cognitive step for goal: {goal[:60]}",
                module="browser_agent",
                action_type="cognitive_step",
                metadata={
                    "goal": goal,
                    "iteration": iteration
                }
            )
        except Exception as e:
            return Response(
                {
                    "action_type": "wait",
                    "wait_after_ms": 5000,
                    "thinking": f"Credit verification failed: {str(e)}",
                    "description": "Failed to verify or burn credits.",
                    "error": str(e),
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
            from agentsettings.models import AgentSettings

            # Resolve model name
            company = getattr(request.user, "company_profile", None)
            startup = request.user.startups.first()
            organization = None
            if company:
                from organization.models import Organization
                organization, _ = Organization.objects.get_or_create(
                    company=company,
                    defaults={"name": company.company_name}
                )
            settings_obj, _ = AgentSettings.objects.get_or_create(
                organization=organization,
                startup=startup,
                defaults={
                    "llm_model": "gemini-2.5-flash",
                    "max_iterations": 30,
                    "autonomy_level": "full_autonomy"
                }
            )
            model_name = settings_obj.llm_model if settings_obj else "gemini-2.5-flash"

            planner = get_planner()
            action = planner.think(
                goal=goal,
                page_state=page_state,
                action_history=action_history,
                iteration=iteration,
                user_response=user_response,
                original_goal=original_goal,
                model_name=model_name,
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
        if request.user and request.user.is_authenticated:
            company = getattr(request.user, "company_profile", None)
            startup = request.user.startups.first()
            organization = None
            if company:
                from organization.models import Organization
                organization = Organization.objects.filter(company=company).first()
            
            from django.db.models import Q
            q_filter = Q()
            if organization is not None or startup is not None:
                if organization is not None:
                    q_filter |= Q(organization=organization)
                if startup is not None:
                    q_filter |= Q(startup=startup)
            else:
                q_filter = Q(organization__isnull=True, startup__isnull=True)
            
            executions = AgentExecution.objects.filter(q_filter).order_by('-started_at')
        else:
            executions = AgentExecution.objects.all().order_by('-started_at')
        serializer = AgentExecutionSerializer(executions, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        if request.user and request.user.is_authenticated:
            company = getattr(request.user, "company_profile", None)
            startup = request.user.startups.first()
            if company:
                from organization.models import Organization
                organization, _ = Organization.objects.get_or_create(
                    company=company,
                    defaults={"name": company.company_name}
                )
                data['organization'] = organization.id
            if startup:
                data['startup'] = startup.id
        serializer = AgentExecutionSerializer(data=data)
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
        conversation_id = request.data.get('conversation_id')
        
        if not sender or not text:
            return Response({"error": "sender and text are required"}, status=status.HTTP_400_BAD_REQUEST)
            
        if not conversation_id or conversation_id == "":
            conversation_id = None
        else:
            import uuid
            try:
                uuid.UUID(str(conversation_id))
            except ValueError:
                conversation_id = None

        chat = AgentChatHistory.objects.create(
            user=request.user if request.user.is_authenticated else None,
            sender=sender,
            text=text,
            conversation_id=conversation_id
        )
        serializer = AgentChatHistorySerializer(chat)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AgentChatHistoryClearView(APIView):
    """
    API View to clear conversational AI chat history.
    """
    def delete(self, request):
        conversation_id = request.query_params.get('conversation_id')
        if conversation_id:
            if request.user.is_authenticated:
                AgentChatHistory.objects.filter(user=request.user, conversation_id=conversation_id).delete()
            else:
                AgentChatHistory.objects.filter(conversation_id=conversation_id).delete()
            return Response({"status": "success", "message": f"Chat history for conversation {conversation_id} cleared."})
        else:
            if request.user.is_authenticated:
                AgentChatHistory.objects.filter(user=request.user).delete()
            else:
                AgentChatHistory.objects.all().delete()
            return Response({"status": "success", "message": "All chat history cleared."})


from Ahrmagent1.models import AgentGoal, AgentMemory, AgentDecision, AgentAction, AgentSchedule, AgentCheckpoint
from Ahrmagent1.serializers import (
    AgentGoalSerializer,
    AgentMemorySerializer,
    AgentDecisionSerializer,
    AgentActionSerializer,
    AgentScheduleSerializer,
    AgentCheckpointSerializer,
)

class AgentGoalListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if request.user and request.user.is_authenticated:
            company = getattr(request.user, "company_profile", None)
            startup = request.user.startups.first()
            organization = None
            if company:
                from organization.models import Organization
                organization = Organization.objects.filter(company=company).first()
            
            from django.db.models import Q
            q_filter = Q()
            if organization is not None or startup is not None:
                if organization is not None:
                    q_filter |= Q(organization=organization)
                if startup is not None:
                    q_filter |= Q(startup=startup)
            else:
                q_filter = Q(organization__isnull=True, startup__isnull=True)
            
            goals = AgentGoal.objects.filter(q_filter).order_by('-created_at')
        else:
            goals = AgentGoal.objects.all().order_by('-created_at')
        serializer = AgentGoalSerializer(goals, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        if request.user and request.user.is_authenticated:
            company = getattr(request.user, "company_profile", None)
            startup = request.user.startups.first()
            if company:
                from organization.models import Organization
                organization, _ = Organization.objects.get_or_create(
                    company=company,
                    defaults={"name": company.company_name}
                )
                data['organization'] = organization.id
            if startup:
                data['startup'] = startup.id
        serializer = AgentGoalSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AgentActiveExecutionView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if request.user and request.user.is_authenticated:
            company = getattr(request.user, "company_profile", None)
            startup = request.user.startups.first()
            organization = None
            if company:
                from organization.models import Organization
                organization = Organization.objects.filter(company=company).first()
            
            from django.db.models import Q
            q_filter = Q()
            if organization is not None or startup is not None:
                if organization is not None:
                    q_filter |= Q(organization=organization)
                if startup is not None:
                    q_filter |= Q(startup=startup)
            else:
                q_filter = Q(organization__isnull=True, startup__isnull=True)
            
            # Stale execution reaper: auto-fail any 'running' or 'pending' execution older than 10 minutes
            from django.utils import timezone as tz
            import datetime
            stale_cutoff = tz.now() - datetime.timedelta(minutes=10)
            stale_execs = AgentExecution.objects.filter(
                agent_type='browser_agent',
                status__in=['pending', 'running'],
                started_at__lt=stale_cutoff
            ).filter(q_filter)
            if stale_execs.exists():
                stale_execs.update(
                    status='failed',
                    completed_at=tz.now()
                )

            active_exec = AgentExecution.objects.filter(
                agent_type='browser_agent',
                status__in=['pending', 'running']
            ).filter(q_filter).order_by('-started_at').first()
        else:
            # Stale execution reaper for unauthenticated requests
            from django.utils import timezone as tz
            import datetime
            stale_cutoff = tz.now() - datetime.timedelta(minutes=10)
            stale_execs = AgentExecution.objects.filter(
                agent_type='browser_agent',
                status__in=['pending', 'running'],
                started_at__lt=stale_cutoff
            )
            if stale_execs.exists():
                stale_execs.update(
                    status='failed',
                    completed_at=tz.now()
                )

            active_exec = AgentExecution.objects.filter(
                agent_type='browser_agent',
                status__in=['pending', 'running']
            ).order_by('-started_at').first()

        if active_exec:
            serializer = AgentExecutionSerializer(active_exec)
            data = serializer.data
            data['active'] = True
            return Response(data)
        
        return Response({"active": False})

class AgentMemoryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, execution_id):
        memories = AgentMemory.objects.filter(execution_id=execution_id).order_by('created_at')
        serializer = AgentMemorySerializer(memories, many=True)
        return Response(serializer.data)

    def post(self, request, execution_id):
        try:
            execution = AgentExecution.objects.get(pk=execution_id)
        except AgentExecution.DoesNotExist:
            return Response({"error": "Execution not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        data['execution'] = execution_id
        
        memory_key = data.get('memory_key')
        memory_type = data.get('memory_type')
        if memory_key and memory_type:
            memory_obj = AgentMemory.objects.filter(
                execution=execution, 
                memory_key=memory_key, 
                memory_type=memory_type
            ).first()
            if memory_obj:
                serializer = AgentMemorySerializer(memory_obj, data=data, partial=True)
                if serializer.is_valid():
                    serializer.save()
                    return Response(serializer.data)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer = AgentMemorySerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AgentDecisionView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, execution_id):
        try:
            execution = AgentExecution.objects.get(pk=execution_id)
        except AgentExecution.DoesNotExist:
            return Response({"error": "Execution not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        data['execution'] = execution_id
        serializer = AgentDecisionSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AgentActionView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, execution_id):
        try:
            execution = AgentExecution.objects.get(pk=execution_id)
        except AgentExecution.DoesNotExist:
            return Response({"error": "Execution not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        data['execution'] = execution_id
        serializer = AgentActionSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AgentCheckpointView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, execution_id):
        checkpoints = AgentCheckpoint.objects.filter(execution_id=execution_id).order_by('-created_at')
        serializer = AgentCheckpointSerializer(checkpoints, many=True)
        return Response(serializer.data)

    def post(self, request, execution_id):
        try:
            execution = AgentExecution.objects.get(pk=execution_id)
        except AgentExecution.DoesNotExist:
            return Response({"error": "Execution not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        data['execution'] = execution_id
        serializer = AgentCheckpointSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AgentScheduleView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if request.user and request.user.is_authenticated:
            company = getattr(request.user, "company_profile", None)
            startup = request.user.startups.first()
            organization = None
            if company:
                from organization.models import Organization
                organization = Organization.objects.filter(company=company).first()
            
            from django.db.models import Q
            q_filter = Q()
            if organization is not None or startup is not None:
                if organization is not None:
                    q_filter |= Q(organization=organization)
                if startup is not None:
                    q_filter |= Q(startup=startup)
            else:
                q_filter = Q(organization__isnull=True, startup__isnull=True)
            
            schedules = AgentSchedule.objects.filter(q_filter).order_by('-id')
        else:
            schedules = AgentSchedule.objects.all().order_by('-id')
        serializer = AgentScheduleSerializer(schedules, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        if request.user and request.user.is_authenticated:
            company = getattr(request.user, "company_profile", None)
            startup = request.user.startups.first()
            if company:
                from organization.models import Organization
                organization, _ = Organization.objects.get_or_create(
                    company=company,
                    defaults={"name": company.company_name}
                )
                data['organization'] = organization.id
            if startup:
                data['startup'] = startup.id
        serializer = AgentScheduleSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
