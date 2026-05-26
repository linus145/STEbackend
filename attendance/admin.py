from django.contrib import admin
from attendance.models import Shift, Attendance, WorkSession

class WorkSessionInline(admin.TabularInline):
    model = WorkSession
    extra = 0

@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('name', 'startup', 'start_time', 'end_time', 'is_deleted')
    list_filter = ('startup', 'is_deleted')

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('employee', 'date', 'status', 'total_work_hours', 'is_late', 'is_deleted')
    list_filter = ('startup', 'status', 'date', 'is_deleted')
    search_fields = ('employee__first_name', 'employee__last_name')
    inlines = [WorkSessionInline]
