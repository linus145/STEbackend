from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from agentsettings.models import AgentSettings, AgentScheduling
from agentsettings.serializers import AgentSettingsSerializer, AgentSchedulingSerializer
from organization.models import Organization

class AgentSettingsDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_tenant_context(self, user):
        company = getattr(user, "company_profile", None)
        startup = user.startups.first()
        organization = None
        if company:
            organization, _ = Organization.objects.get_or_create(
                company=company,
                defaults={"name": company.company_name}
            )
        return organization, startup

    def get(self, request):
        organization, startup = self.get_tenant_context(request.user)
        
        # Get or create active settings
        settings_obj, created = AgentSettings.objects.get_or_create(
            organization=organization,
            startup=startup,
            defaults={
                "llm_model": "gemini-2.5-flash",
                "temperature": 0.1,
                "max_iterations": 30,
                "autonomy_level": "full_autonomy"
            }
        )
        
        serializer = AgentSettingsSerializer(settings_obj)
        return Response(serializer.data)

    def patch(self, request):
        organization, startup = self.get_tenant_context(request.user)
        settings_obj, _ = AgentSettings.objects.get_or_create(
            organization=organization,
            startup=startup
        )
        
        serializer = AgentSettingsSerializer(settings_obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AgentSchedulingDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_tenant_context(self, user):
        company = getattr(user, "company_profile", None)
        startup = user.startups.first()
        organization = None
        if company:
            organization, _ = Organization.objects.get_or_create(
                company=company,
                defaults={"name": company.company_name}
            )
        return organization, startup

    def get(self, request):
        organization, startup = self.get_tenant_context(request.user)
        
        # Get or create active scheduling
        scheduling_obj, created = AgentScheduling.objects.get_or_create(
            organization=organization,
            startup=startup,
            defaults={
                "enabled": False,
                "recurrence": "daily",
                "execution_time": "09:00:00",
                "task_type": "payroll_runs",
                "notification_email": request.user.email
            }
        )
        
        serializer = AgentSchedulingSerializer(scheduling_obj)
        return Response(serializer.data)

    def patch(self, request):
        organization, startup = self.get_tenant_context(request.user)
        scheduling_obj, _ = AgentScheduling.objects.get_or_create(
            organization=organization,
            startup=startup
        )
        
        serializer = AgentSchedulingSerializer(scheduling_obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
