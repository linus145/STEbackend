import traceback
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from startups.models import CompanyProfile
from .services import AIAgentService

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
                return Response({"status": "error", "message": "Company profile not found."}, status=400)

            try:
                job = AIAgentService.execute_job_post(company, prompt)
                
                return Response({
                    "status": "success",
                    "message": f"Agent successfully drafted and published the {job.title} position.",
                    "details": {
                        "job_id": str(job.id),
                        "job_title": job.title,
                        "platforms_posted": ["B2linq Network"],
                        "agent_notes": "AI optimized the job description and automatically matched the required skills."
                    }
                })
            except Exception as e:
                traceback.print_exc()
                return Response({
                    "status": "error",
                    "message": f"Agent failed to execute task: {str(e)}"
                }, status=500)

        elif task_type == "schedule_interview":
            candidate_id = payload.get("candidate_id")
            details = AIAgentService.execute_schedule_interview(candidate_id)
            return Response({
                "status": "success",
                "message": "Interview scheduling emails sent via AI Agent.",
                "details": details
            })
        else:
            return Response({
                "status": "error",
                "message": f"Unknown task type: {task_type}"
            }, status=400)
