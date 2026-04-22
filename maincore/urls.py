"""
URL configuration for maincore project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include

# Customize Admin Site
admin.site.site_header = "BE2linq Admin Panel"
admin.site.site_title = "BE2linq Admin"
admin.site.index_title = "Network Architect Control Center"


# Reorder Admin Apps (Move UserAccounts to top)
def get_app_list(self, request, app_label=None):
    app_dict = self._build_app_dict(request, app_label)
    app_list = sorted(app_dict.values(), key=lambda x: x["name"].lower())

    # Custom priority order
    priority_apps = ["useraccounts", "posts", "notifications", "comments"]

    sorted_app_list = []
    # Add priority apps first
    for label in priority_apps:
        for i, app in enumerate(app_list):
            if app["app_label"] == label:
                sorted_app_list.append(app_list.pop(i))
                break

    # Add the rest
    sorted_app_list.extend(app_list)
    return sorted_app_list


admin.AdminSite.get_app_list = get_app_list

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("useraccounts.urls")),
    path("api/founders/", include("founders.urls")),
    path("api/investors/", include("investors.urls")),
    path("api/startups/", include("startups.urls")),
    path("api/posts/", include("posts.urls")),
    path("api/interactions/", include("interactions.urls")),
    path("api/chat/", include("chat.urls")),
    path("api/notifications/", include("notifications.urls")),
    path("api/comments/", include("comments.urls")),
    path("api/jobs/", include("jobs.urls")),
    path("api/news/", include("news.urls")),
    path("api/subscription/", include("subscription.urls")),
    path("api/ai/", include("AI.urls")),
]
