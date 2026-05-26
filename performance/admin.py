from django.contrib import admin
from performance.models import (
    KPI, Goal, PerformanceReview, EmployeeFeedback, 
    PerformanceCycle, Competency, CompetencyScore, 
    PerformanceWeightConfiguration, PerformanceScoreBreakdown
)

@admin.register(KPI)
class KPIAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'target_value', 'unit', 'is_deleted')
    list_filter = ('organization', 'is_deleted')
    list_editable = ('is_deleted',)

@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ('title', 'employee', 'status', 'progress_percentage', 'due_date', 'is_deleted')
    list_filter = ('status', 'due_date', 'is_deleted')
    search_fields = ('title', 'employee__first_name', 'employee__last_name')
    list_editable = ('is_deleted',)

@admin.register(PerformanceReview)
class PerformanceReviewAdmin(admin.ModelAdmin):
    list_display = ('employee', 'reviewer', 'rating', 'status', 'review_period_end', 'is_deleted')
    list_filter = ('status', 'rating', 'is_deleted')
    search_fields = ('employee__first_name', 'employee__last_name')
    list_editable = ('is_deleted',)

@admin.register(PerformanceCycle)
class PerformanceCycleAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'start_date', 'due_date', 'is_active', 'is_deleted')
    list_filter = ('is_active', 'is_deleted')
    list_editable = ('is_deleted',)

@admin.register(Competency)
class CompetencyAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'category', 'is_deleted')
    list_filter = ('category', 'is_deleted')
    list_editable = ('is_deleted',)

@admin.register(CompetencyScore)
class CompetencyScoreAdmin(admin.ModelAdmin):
    list_display = ('review', 'competency', 'score', 'weight', 'is_deleted')
    list_filter = ('is_deleted',)
    list_editable = ('is_deleted',)

@admin.register(PerformanceWeightConfiguration)
class PerformanceWeightConfigurationAdmin(admin.ModelAdmin):
    list_display = ('organization', 'goal_weight', 'feedback_weight', 'is_deleted')
    list_filter = ('is_deleted',)
    list_editable = ('is_deleted',)

@admin.register(PerformanceScoreBreakdown)
class PerformanceScoreBreakdownAdmin(admin.ModelAdmin):
    list_display = ('review', 'avg_goal_progress', 'avg_feedback_rating', 'final_calculated_score', 'is_deleted')
    list_filter = ('is_deleted',)
    list_editable = ('is_deleted',)

@admin.register(EmployeeFeedback)
class EmployeeFeedbackAdmin(admin.ModelAdmin):
    list_display = ('review', 'provider', 'feedback_type', 'rating', 'is_anonymous', 'is_deleted')
    list_filter = ('feedback_type', 'is_anonymous', 'is_deleted')
    list_editable = ('is_deleted',)
