from django.urls import path
from . import views

app_name = "following"

urlpatterns = [
    # ── User Follow ──
    path("toggle/", views.ToggleFollowView.as_view(), name="toggle-follow"),
    path("followers/", views.FollowersListView.as_view(), name="my-followers"),
    path("followers/<uuid:user_id>/", views.FollowersListView.as_view(), name="user-followers"),
    path("following/", views.FollowingListView.as_view(), name="my-following"),
    path("following/<uuid:user_id>/", views.FollowingListView.as_view(), name="user-following"),
    path("counts/", views.FollowCountsView.as_view(), name="my-counts"),
    path("counts/<uuid:user_id>/", views.FollowCountsView.as_view(), name="user-counts"),

    # ── Company Follow ──
    path("company/toggle/", views.ToggleCompanyFollowView.as_view(), name="toggle-company-follow"),
    path("company/followers/<uuid:company_id>/", views.CompanyFollowersListView.as_view(), name="company-followers"),
    path("company/counts/<uuid:company_id>/", views.CompanyFollowCountsView.as_view(), name="company-counts"),
    path("company/my-followed/", views.MyFollowedCompaniesView.as_view(), name="my-followed-companies"),
]
