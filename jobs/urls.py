from django.urls import path
from . import views

urlpatterns = [

    # ─── Public Job Browsing ────────────────────────────────────
    path("posts/", views.PublicJobListView.as_view(), name="public-job-list"),
    path("posts/<uuid:job_id>/", views.JobPostDetailView.as_view(), name="public-job-detail"),

    # ─── Recruiter Job Management ───────────────────────────────
    path("my-posts/", views.RecruiterJobListView.as_view(), name="recruiter-job-list"),
    path("my-posts/<uuid:job_id>/", views.RecruiterJobDetailView.as_view(), name="recruiter-job-detail"),

    # ─── Applications ───────────────────────────────────────────
    path("posts/<uuid:job_id>/apply/", views.ApplyToJobView.as_view(), name="job-apply"),
    path("posts/<uuid:job_id>/applications/", views.JobApplicationsView.as_view(), name="job-applications"),
    path("applications/<uuid:application_id>/status/", views.UpdateApplicationStatusView.as_view(), name="update-application-status"),
    path("applications/<uuid:application_id>/detail/", views.JobApplicationDetailView.as_view(), name="job-application-detail"),
    path("posts/<uuid:job_id>/analyze-resumes/", views.AnalyzeResumesView.as_view(), name="job-analyze-resumes"),
    path("my-applications/", views.MyApplicationsView.as_view(), name="my-applications"),

    # ─── Dashboard Stats ────────────────────────────────────────
    path("dashboard/stats/", views.RecruiterDashboardStatsView.as_view(), name="recruiter-dashboard-stats"),

    # ─── Skills ──────────────────────────────────────────────────
    path("skills/", views.SkillListView.as_view(), name="skill-list"),
]