from django.urls import path
from .views import PostCommentsListView, CommentCreateView

urlpatterns = [
    path('post/<uuid:post_id>/', PostCommentsListView.as_view(), name='post-comments'),
    path('create/', CommentCreateView.as_view(), name='comment-create'),
]
