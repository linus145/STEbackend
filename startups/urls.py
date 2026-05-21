from django.urls import path
from startups.views import (
    StartupListView,
    MyStartupsView,
    StartupDetailView,
    CompanyRegisterView,
    CompanyProfileView,
    CompanyHRProfileView,
    CompanyHRProfileListCreateView,
    CompanyHRProfileDetailView,
    CompanyCheckView,
    CompanyLoginView
)

app_name = "startups"

urlpatterns = [
    # ─── Company Profile ────────────────────────────────────────
    path("company/register/", CompanyRegisterView.as_view(), name="company-register"),
    path("company/login/", CompanyLoginView.as_view(), name="company-login"),
    path("company/me/", CompanyProfileView.as_view(), name="company-profile"),
    path("company/hr-profile/", CompanyHRProfileView.as_view(), name="company-hr-profile"),
    path("company/hr-profiles/", CompanyHRProfileListCreateView.as_view(), name="company-hr-profiles-list-create"),
    path("company/hr-profiles/<uuid:pk>/", CompanyHRProfileDetailView.as_view(), name="company-hr-profile-detail"),
    path("company/check/", CompanyCheckView.as_view(), name="company-check"),
    # ─── Startups ───────────────────────────────────────────────
    path("", StartupListView.as_view(), name="startup_list"),
    path(
        "me/", MyStartupsView.as_view(), name="my_startups"
    ),  # GET and POST custom startups
    path(
        "<uuid:startup_id>/", StartupDetailView.as_view(), name="startup_detail"
    ),  # GET, PUT, DELETE
]
