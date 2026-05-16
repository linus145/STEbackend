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
from maincore.upload_views import ImageUploadView


# Customize Admin Site
admin.site.site_header = "B2linq Admin Panel"
admin.site.site_title = "B2linq Admin"
admin.site.index_title = "Network Architect Control Center"


# Reorder and Group Admin Apps
def get_app_list(self, request, app_label=None):
    app_dict = self._build_app_dict(request, app_label)
    
    # HR related apps to aggregate
    hr_app_labels = [
        "employees", "attendance", "leave_management", 
        "organization", "payroll", "performance",
        "AIAgents", "Ahrmagent1", "Ahrmagent2"
    ]
    
    hr_models = []
    hr_app_entry = None
    
    # Collect all models from HR apps and remove them from original dict
    for label in hr_app_labels:
        if label in app_dict:
            app = app_dict.pop(label)
            hr_models.extend(app["models"])
            if not hr_app_entry:
                # Copy the app structure but we'll override the list of models
                hr_app_entry = app.copy()
    
    # Create the aggregated HR Tool entry
    if hr_app_entry:
        hr_app_entry["name"] = "HR Tool"
        hr_app_entry["app_label"] = "hr_tool"
        # Sort models by name and remove duplicates just in case
        seen_models = set()
        unique_models = []
        for model in hr_models:
            model_key = f"{model.get('object_name')}"
            if model_key not in seen_models:
                unique_models.append(model)
                seen_models.add(model_key)
        
        hr_app_entry["models"] = sorted(unique_models, key=lambda x: x["name"])
        app_dict["hr_tool"] = hr_app_entry

    app_list = sorted(app_dict.values(), key=lambda x: x["name"].lower())

    # Custom priority order
    priority_apps = ["useraccounts", "hr_tool", "posts", "notifications", "comments"]

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

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)


urlpatterns = [
    path("admin/", admin.site.urls),
    # Server-side image upload endpoint
    path("api/upload/image/", ImageUploadView.as_view(), name="image-upload"),
    # Swagger UI endpoints
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
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
    path("api/seo/", include("seo.urls")),
    path("api/public/", include("publicpages.urls")),
    
    #AI
    path("api/ai/", include("AI.urls")),
    path("api/AIInterview/", include("AIInterview.urls")),
    path("api/AIrounds/", include("AIrounds.urls")),
    path("api/proctoring/", include("Aisecurity.urls")),

    #agents
    path("api/AIAgents/", include("AIAgents.urls")),
    path("api/autonomousagent1/", include("Ahrmagent1.urls")),
    path("api/hrmagent2/", include("Ahrmagent2.urls")),

    #HR
    path("api/employees/", include("employees.urls")),
    path("api/attendance/", include("attendance.urls")),
    path("api/leave_management/", include("leave_management.urls")),
    path("api/organization/", include("organization.urls")),
    path("api/payroll/", include("payroll.urls")),
    path("api/performance/", include("performance.urls")),
    path("api/search/", include("searchfilters.urls")),
]
from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
