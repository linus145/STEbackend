from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from agentsettings.models import AgentSettings, AgentScheduling, AgentSchedulingLog
from agentsettings.serializers import AgentSettingsSerializer, AgentSchedulingSerializer, AgentSchedulingLogSerializer
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
                "notification_email": request.user.email,
                "command": '[{"task": "payroll_runs", "recurrence": "monthly", "command": "need payslip approval", "execution_time": "18:50:00"}]',
                "max_executions": 5,
                "run_count": 0
            }
        )
        
        # Upgrade legacy default command to new step format
        if scheduling_obj.command == "Execute default task audit and sync pipeline" or not scheduling_obj.command.strip():
            scheduling_obj.command = '[{"task": "payroll_runs", "recurrence": "monthly", "command": "need payslip approval", "execution_time": "18:50:00"}]'
            scheduling_obj.save()
        
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

class AgentSchedulingTriggerView(APIView):
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

    def post(self, request):
        organization, startup = self.get_tenant_context(request.user)
        
        scheduling_obj = AgentScheduling.objects.filter(
            organization=organization,
            startup=startup
        ).first()
        
        if not scheduling_obj:
            return Response({"error": "No scheduling profile found to trigger."}, status=status.HTTP_404_NOT_FOUND)
            
        import threading
        from django.db import close_old_connections
        from agentsettings.tasks import run_schedule_manually
        
        def run_in_background(sched_id):
            close_old_connections()
            try:
                run_schedule_manually(sched_id)
            except Exception as thread_ex:
                import logging
                logging.getLogger("agentsettings.views").error(
                    f"Error in manual schedule run thread: {str(thread_ex)}"
                )
            finally:
                close_old_connections()
                
        # Trigger manual execution immediately via thread (failsafe against Celery stale registries)
        thread = threading.Thread(target=run_in_background, args=(scheduling_obj.id,))
        thread.daemon = True
        thread.start()
        
        return Response({"message": "Sample run triggered successfully! The agent is executing the steps and sending the report email."})

class AgentSchedulingLogListView(APIView):
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
        scheduling_obj = AgentScheduling.objects.filter(
            organization=organization,
            startup=startup
        ).first()
        
        if not scheduling_obj:
            return Response([])

        # Stale log reaper: auto-fail any 'running' log older than 10 minutes
        # This is a safety net in case frontend handlers fail to update the status
        from django.utils import timezone as tz
        import datetime
        stale_cutoff = tz.now() - datetime.timedelta(minutes=10)
        stale_logs = AgentSchedulingLog.objects.filter(
            schedule=scheduling_obj,
            status='running',
            started_at__lt=stale_cutoff
        )
        if stale_logs.exists():
            stale_logs.update(
                status='failed',
                completed_at=tz.now(),
                error_message='Auto-failed: execution exceeded 10-minute timeout.'
            )

        logs = AgentSchedulingLog.objects.filter(schedule=scheduling_obj).order_by('-started_at')
        serializer = AgentSchedulingLogSerializer(logs, many=True)
        return Response(serializer.data)

    def post(self, request):
        organization, startup = self.get_tenant_context(request.user)
        scheduling_obj = AgentScheduling.objects.filter(
            organization=organization,
            startup=startup
        ).first()
        
        if not scheduling_obj:
            return Response({"error": "No scheduling profile found to create logs."}, status=status.HTTP_404_NOT_FOUND)
            
        data = request.data.copy()
        data['schedule'] = scheduling_obj.id
        
        serializer = AgentSchedulingLogSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AgentSchedulingLogDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            log = AgentSchedulingLog.objects.get(pk=pk)
        except AgentSchedulingLog.DoesNotExist:
            return Response({"error": "Log record not found."}, status=status.HTTP_404_NOT_FOUND)
            
        old_status = log.status
        serializer = AgentSchedulingLogSerializer(log, data=request.data, partial=True)
        if serializer.is_valid():
            log = serializer.save()
            
            # Send report email if status transitioned from 'running' to 'success' or 'failed'
            if old_status == 'running' and log.status in ['success', 'failed']:
                if log.schedule:
                    try:
                        from agentsettings.tasks import send_agent_execution_report
                        send_agent_execution_report(
                            schedule=log.schedule,
                            execution=log,
                            actions_performed=log.actions_performed,
                            error_message=log.error_message if log.status == 'failed' else None
                        )
                    except Exception as email_err:
                        import logging
                        logging.getLogger('agentsettings.views').error(
                            f"Failed to send execution report email for log {pk}: {email_err}"
                        )
            
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
