from django.urls import path
from .views import PageSEOQueryView

urlpatterns = [
    path('', PageSEOQueryView.as_view(), name='page-seo-query'),
]