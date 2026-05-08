from django.contrib import admin
from AIrounds.models import InterviewSession, InterviewRound, InterviewQuestion, CandidateInterviewLink

class InterviewQuestionInline(admin.TabularInline):
    model = InterviewQuestion
    extra = 0
    fields = ('question_text', 'question_type', 'mcq_options', 'expected_topics')

class InterviewRoundInline(admin.StackedInline):
    model = InterviewRound
    extra = 0
    fields = ('strategy_tier', 'designation', 'difficulty', 'question_format', 'programming_language', 'status', 'timer_seconds', 'max_questions', 'round_score')
    show_change_link = True

class CandidateInterviewLinkInline(admin.StackedInline):
    model = CandidateInterviewLink
    extra = 0
    readonly_fields = ('token', 'exam_username', 'exam_password', 'created_at')
    fields = ('token', 'exam_username', 'exam_password', 'status', 'expires_at', 'started_at', 'completed_at', 'ip_address', 'created_at')

@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate_email', 'job_title', 'status', 'overall_score', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('candidate__email', 'job_title', 'id')
    readonly_fields = ('invite_token', 'created_at', 'updated_at')
    inlines = [InterviewRoundInline, CandidateInterviewLinkInline]

    def candidate_email(self, obj):
        return obj.candidate.email
    candidate_email.short_description = 'Candidate Email'

@admin.register(InterviewRound)
class InterviewRoundAdmin(admin.ModelAdmin):
    list_display = ('id', 'session_id', 'strategy_tier', 'designation', 'difficulty', 'question_format', 'programming_language', 'status', 'round_score')
    list_filter = ('strategy_tier', 'difficulty', 'question_format', 'status')
    search_fields = ('session__id', 'designation')
    inlines = [InterviewQuestionInline]

    def session_id(self, obj):
        return obj.session.id
    session_id.short_description = 'Session ID'

@admin.register(InterviewQuestion)
class InterviewQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'round_id', 'question_text_short', 'question_type')
    list_filter = ('question_type', 'asked_at')
    search_fields = ('question_text', 'candidate_answer')

    def round_id(self, obj):
        return obj.round.id
    round_id.short_description = 'Round ID'

    def question_text_short(self, obj):
        return obj.question_text[:50] + '...' if len(obj.question_text) > 50 else obj.question_text
    question_text_short.short_description = 'Question'

@admin.register(CandidateInterviewLink)
class CandidateInterviewLinkAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate_email', 'exam_username', 'exam_password', 'session_job', 'status', 'expires_at', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('session__candidate__email', 'token', 'exam_username')
    readonly_fields = ('token', 'exam_username', 'exam_password', 'created_at')

    def candidate_email(self, obj):
        return obj.session.candidate.email
    candidate_email.short_description = 'Candidate'

    def session_job(self, obj):
        return obj.session.job_title
    session_job.short_description = 'Job Title'
