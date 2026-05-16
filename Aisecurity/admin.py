from django.contrib import admin
from .models import ProctoringSession, ViolationLog

class ViolationInline(admin.StackedInline):
    model = ViolationLog
    extra = 0
    readonly_fields = ('timestamp',)

@admin.register(ProctoringSession)
class ProctoringSessionAdmin(admin.ModelAdmin):
    list_display = ('session', 'is_active', 'integrity_score', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('session__candidate__email',)
    inlines = [ViolationInline]
    readonly_fields = ('created_at', 'updated_at')

@admin.register(ViolationLog)
class ViolationLogAdmin(admin.ModelAdmin):
    list_display = ('violation_type', 'severity', 'timestamp', 'proctoring_session')
    list_filter = ('violation_type', 'severity', 'timestamp')
    search_fields = ('proctoring_session__session__candidate__email', 'metadata')
    readonly_fields = ('timestamp',)
