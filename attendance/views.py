from rest_framework import viewsets, filters, status, decorators
from rest_framework.response import Response
from django.utils import timezone
from attendance.models import Shift, Attendance, WorkSession
from attendance.serializers import ShiftSerializer, AttendanceSerializer, WorkSessionSerializer
from organization.views import StartupTenantMixin

class ShiftViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Shift.objects.all()
    serializer_class = ShiftSerializer

    def perform_create(self, serializer):
        user = self.request.user
        company = getattr(user, 'company_profile', None)
        organization = None
        if company:
            from organization.models import Organization
            organization = Organization.objects.filter(company=company).first()

        if organization:
            # Heal organization startup if not set
            if not organization.startup:
                from startups.models import Startup
                st = Startup.objects.filter(founder=user, name=company.company_name).first()
                if not st:
                    st = Startup.objects.filter(founder=user).first()
                if not st:
                    st = Startup.objects.first()
                if not st:
                    st = Startup.objects.create(
                        founder=user,
                        name=company.company_name,
                        pitch=company.description or f"Startup profile for {company.company_name}",
                        industry=company.industry or "Technology",
                        stage="Bootstrap",
                        website_url=company.website,
                        logo_url=company.logo_url
                    )
                organization.startup = st
                organization.save()
            startup = organization.startup
        else:
            startup = user.startups.first()

        serializer.save(startup=startup, organization=organization)

class AttendanceViewSet(StartupTenantMixin, viewsets.ModelViewSet):
    queryset = Attendance.objects.select_related('employee').prefetch_related('sessions').all()
    serializer_class = AttendanceSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['employee__first_name', 'employee__last_name', 'date']
    ordering_fields = ['date']

    def perform_destroy(self, instance):
        instance.hard_delete()

    @decorators.action(detail=False, methods=['post'])
    def check_in(self, request):
        """
        Check-in action for the authenticated user (if they are an employee).
        """
        employee = getattr(request.user, 'employee_profile', None)
        if not employee:
            return Response({"error": "User is not an employee"}, status=status.HTTP_400_BAD_REQUEST)
        
        today = timezone.now().date()
        
        # Check all_objects to account for soft-deleted records and avoid IntegrityError
        attendance = Attendance.all_objects.filter(employee=employee, date=today).first()
        if attendance:
            if attendance.is_deleted:
                attendance.restore()
            # Ensure startup is set correctly if it wasn't
            changed = False
            if attendance.startup != employee.startup:
                attendance.startup = employee.startup
                changed = True
            if getattr(employee, 'organization', None) and attendance.organization != employee.organization:
                attendance.organization = employee.organization
                changed = True
            if changed:
                attendance.save()
        else:
            attendance = Attendance.objects.create(
                employee=employee,
                date=today,
                startup=employee.startup,
                organization=getattr(employee, 'organization', None)
            )
        
        # Check if there's an active session
        active_session = attendance.sessions.filter(check_out__isnull=True).first()
        if active_session:
            return Response({"error": "Already checked in"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get startup shift or create default
        shift = Shift.objects.filter(startup=employee.startup).first()
        if not shift:
            from datetime import time
            shift = Shift.objects.create(
                startup=employee.startup,
                name="Standard Day Shift",
                start_time=time(9, 0),
                end_time=time(18, 0),
                break_duration=60,
                grace_period=15,
                min_hours_full_day=8.00,
                min_hours_half_day=4.00
            )

        # Create session
        WorkSession.objects.create(attendance=attendance)

        # Check late check-in
        now = timezone.now()
        local_now = timezone.localtime(now)
        local_time = local_now.time()
        
        # If it's the first check-in session today, evaluate is_late
        is_first_session = attendance.sessions.count() <= 1
        if is_first_session and shift:
            from datetime import datetime, date, timedelta
            shift_start_dt = datetime.combine(date.today(), shift.start_time)
            late_threshold_dt = shift_start_dt + timedelta(minutes=shift.grace_period)
            late_threshold_time = late_threshold_dt.time()
            
            if local_time > late_threshold_time:
                attendance.is_late = True
                attendance.status = 'LATE'
                attendance.save()

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
        
        # Recalculate total hours
        sessions = attendance.sessions.filter(check_out__isnull=False)
        total_seconds = sum([(s.check_out - s.check_in).total_seconds() for s in sessions])
        total_hours = round(total_seconds / 3600, 2)
        attendance.total_work_hours = total_hours
        # Get shift
        shift = Shift.objects.filter(startup=employee.startup).first()
        
        # Calculate overtime hours
        expected_hours = 8.00
        if shift:
            from datetime import datetime, date
            expected_seconds = (datetime.combine(date.today(), shift.end_time) - datetime.combine(date.today(), shift.start_time)).total_seconds()
            expected_seconds -= shift.break_duration * 60
            expected_hours = max(0.00, round(expected_seconds / 3600, 2))

        if total_hours > expected_hours:
            attendance.overtime_hours = round(total_hours - expected_hours, 2)
        else:
            attendance.overtime_hours = 0.00

        if shift:
            if total_hours >= float(shift.min_hours_full_day):
                if attendance.is_late:
                    attendance.status = 'LATE'
                else:
                    attendance.status = 'PRESENT'
            elif total_hours >= float(shift.min_hours_half_day):
                attendance.status = 'HALF_DAY'
            else:
                attendance.status = 'ABSENT'
        else:
            if total_hours >= 8.00:
                attendance.status = 'PRESENT'
            elif total_hours >= 4.00:
                attendance.status = 'HALF_DAY'
            else:
                attendance.status = 'ABSENT'

        attendance.save()
        return Response(AttendanceSerializer(attendance).data)
