from django.urls import path
from .views import (
    JobSearchView,
    DashboardJobSearchView,
    ApplicationSearchView,
    GlobalSearchView,
    GlobalNewsSearchView,
    GlobalPostSearchView,
    GlobalUserSearchView,
)

urlpatterns = [
    path("jobs/", JobSearchView.as_view(), name="search-jobs"),
    path("jobs/dashboard/", DashboardJobSearchView.as_view(), name="search-jobs-dashboard"),
    path("applications/", ApplicationSearchView.as_view(), name="search-applications"),
    path("global/", GlobalSearchView.as_view(), name="global-search"),
    path("global/news/", GlobalNewsSearchView.as_view(), name="global-search-news"),
    path("global/posts/", GlobalPostSearchView.as_view(), name="global-search-posts"),
    path("global/users/", GlobalUserSearchView.as_view(), name="global-search-users"),
]
