from django.urls import path
from .views import PostListView, PostCreateView, PostDetailView, ImageKitAuthView, UserPostListView

app_name = 'posts'

urlpatterns = [
    path('', PostListView.as_view(), name='post-list'),
    path('user/<uuid:user_id>/', UserPostListView.as_view(), name='user-posts'),
    path('create/', PostCreateView.as_view(), name='post-create'),
    path('imagekit-auth/', ImageKitAuthView.as_view(), name='imagekit-auth'),
    path('<uuid:post_id>/', PostDetailView.as_view(), name='post-detail'),
]
