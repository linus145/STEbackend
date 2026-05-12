from django.contrib import admin
from attendance.models import Shift, Attendance, WorkSession

class WorkSessionInline(admin.TabularInline):
    model = WorkSession
    extra = 0

@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ('name', 'startup', 'start_time', 'end_time')
    list_filter = ('startup',)

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'status', 'total_work_hours', 'is_late')
    list_filter = ('startup', 'status', 'date')
    search_fields = ('employee__first_name', 'employee__last_name')
    inlines = [WorkSessionInline]
