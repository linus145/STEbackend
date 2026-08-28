from django.urls import path
from .views import (
    CompanyProfileView,
    UserCompanyCheckView,
    CompanyPageCreateView,
    CompanyPostsView,
    CompanyPostDetailView,
    CompanyPostBoostView,
    CompanyJobsView,
    ExploreCompaniesView,
)

app_name = "comppages"

urlpatterns = [
    # User / Authentication company checks
    path("me/", UserCompanyCheckView.as_view(), name="user-company-check"),
    path("create/", CompanyPageCreateView.as_view(), name="company-page-create"),
    path("explore/", ExploreCompaniesView.as_view(), name="company-explore"),
    
    # Sub-resources by slug
    path("<str:company_slug>/posts/<uuid:post_id>/boost/", CompanyPostBoostView.as_view(), name="company-post-boost"),
    path("<str:company_slug>/posts/<uuid:post_id>/", CompanyPostDetailView.as_view(), name="company-post-detail"),
    path("<str:company_slug>/posts/", CompanyPostsView.as_view(), name="company-posts"),
    path("<str:company_slug>/jobs/", CompanyJobsView.as_view(), name="company-jobs"),
    
    # Dynamic profile view (by slug or UUID)
    path("<str:company_slug>/", CompanyProfileView.as_view(), name="company-profile"),
    path("<str:company_slug>", CompanyProfileView.as_view(), name="company-profile-noslash"),
]
