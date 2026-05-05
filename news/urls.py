from django.urls import path
from .views import NewsListView, NewsCreateView, NewsDetailView

app_name = 'news'

urlpatterns = [
    path('', NewsListView.as_view(), name='news-list'),
    path('create/', NewsCreateView.as_view(), name='news-create'),
    path('<uuid:pk>/', NewsDetailView.as_view(), name='news-detail'),
]