import traceback
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from startups.models import CompanyProfile
from AIAgents.services import AIAgentService


class AgentTaskExecuteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        task_type = request.data.get("task_type")
        payload = request.data.get("payload", {})

        if task_type == "post_job" or task_type == "agentic_job_post":
            user = request.user
            prompt = payload.get("prompt", "Post a job for a Software Engineer")

            try:
                company = CompanyProfile.objects.get(owner=user)
            except CompanyProfile.DoesNotExist:
                return Response(
                    {"status": "error", "message": "Company profile not found."},
                    status=400,
                )

            from AIAgents.tasks import task_execute_job_post

            celery_task = task_execute_job_post.delay(company.id, prompt)

            return Response(
                {
                    "status": "success",
                    "message": "AI Agent has started drafting the job position in the background.",
                    "task_id": celery_task.id,
                    "details": {
                        "agent_notes": "AI is currently optimizing the job description and matching skills. You can track progress via task history."
                    },
                },
                status=202,
            )

        elif task_type == "schedule_interview":
            candidate_id = payload.get("candidate_id")
            details = AIAgentService.execute_schedule_interview(candidate_id)
            return Response(
                {
                    "status": "success",
                    "message": "Interview scheduling emails sent via AI Agent.",
                    "details": details,
                }
            )

        elif task_type == "talent_search":
            query = payload.get("query", "")
            from AIAgents.tasks import task_execute_talent_search

            celery_task = task_execute_talent_search.delay(query, request.user.id)

            return Response(
                {
                    "status": "success",
                    "message": "AI Agent is analyzing your query and searching for matching talent.",
                    "task_id": celery_task.id,
                    "details": {
                        "agent_notes": "Searching across the platform for the best fits. Results will appear in your search history shortly."
                    },
                },
                status=202,
            )
        elif task_type == "get_search_history":
            history = AIAgentService.get_talent_search_history(request.user)
            return Response({"status": "success", "details": history})
        else:
            return Response(
                {"status": "error", "message": f"Unknown task type: {task_type}"},
                status=400,
            )
