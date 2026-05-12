from rest_framework import viewsets, filters, status, decorators
from rest_framework.response import Response
from django.utils import timezone
from attendance.models import Shift, Attendance, WorkSession
from attendance.serializers import ShiftSerializer, AttendanceSerializer, WorkSessionSerializer
from organization.views import StartupTenantMixin

class ShiftViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Shift.objects.all()
    serializer_class = ShiftSerializer

class AttendanceViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Attendance.objects.select_related('employee').prefetch_related('sessions').all()
    serializer_class = AttendanceSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['employee__first_name', 'employee__last_name', 'date']
    ordering_fields = ['date']

    @decorators.action(detail=False, methods=['post'])
    def check_in(self, request):
        """
        Check-in action for the authenticated user (if they are an employee).
        """
        employee = getattr(request.user, 'employee_profile', None)
        if not employee:
            return Response({"error": "User is not an employee"}, status=status.HTTP_400_BAD_REQUEST)
        
        today = timezone.now().date()
        attendance, _ = Attendance.objects.get_or_create(
            employee=employee,
            date=today,
            startup=employee.startup
        )
        
        # Check if there's an active session
        active_session = attendance.sessions.filter(check_out__isnull=True).first()
        if active_session:
            return Response({"error": "Already checked in"}, status=status.HTTP_400_BAD_REQUEST)
        
        WorkSession.objects.create(attendance=attendance)
        return Response(AttendanceSerializer(attendance).data, status=status.HTTP_201_CREATED)

    @decorators.action(detail=False, methods=['post'])
    def check_out(self, request):
        """
        Check-out action.
        """
        employee = getattr(request.user, 'employee_profile', None)
        if not employee:
            return Response({"error": "User is not an employee"}, status=status.HTTP_400_BAD_REQUEST)
        
        today = timezone.now().date()
        attendance = Attendance.objects.filter(employee=employee, date=today).first()
        if not attendance:
            return Response({"error": "No attendance record found for today"}, status=status.HTTP_400_BAD_REQUEST)
        
        active_session = attendance.sessions.filter(check_out__isnull=True).first()
        if not active_session:
            return Response({"error": "Not checked in"}, status=status.HTTP_400_BAD_REQUEST)
        
        active_session.check_out = timezone.now()
        active_session.save()
        
        # Recalculate total hours (simplified)
        sessions = attendance.sessions.filter(check_out__isnull=False)
        total_seconds = sum([(s.check_out - s.check_in).total_seconds() for s in sessions])
        attendance.total_work_hours = round(total_seconds / 3600, 2)
        attendance.save()
        
        return Response(AttendanceSerializer(attendance).data)
