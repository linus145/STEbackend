from django.contrib import admin
from performance.models import KPI, Goal, PerformanceReview, EmployeeFeedback

@admin.register(KPI)
class KPIAdmin(admin.ModelAdmin):
    list_display = ('name', 'startup', 'target_value', 'unit')
    list_filter = ('startup',)

@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ('title', 'employee', 'status', 'progress_percentage', 'due_date')
    list_filter = ('status', 'due_date')
    search_fields = ('title', 'employee__first_name', 'employee__last_name')

@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ('employee', 'reviewer', 'rating', 'status', 'review_period_end')
    list_filter = ('status', 'rating')
    search_fields = ('employee__first_name', 'employee__last_name')

admin.site.register(EmployeeFeedback)
