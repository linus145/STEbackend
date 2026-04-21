from django.urls import path
from . import views

app_name = 'interactions'

urlpatterns = [
    path('likes/toggle/', views.ToggleLikeView.as_view(), name='toggle-like'),
    path('comments/', views.CommentListCreateView.as_view(), name='comments-list-create'),
    path('comments/<uuid:comment_id>/', views.CommentDeleteView.as_view(), name='delete-comment'),
    
    # Networking
    path('network/people/', views.NetworkPeopleView.as_view(), name='network-people'),
    path('network/my-connections/', views.MyConnectionsView.as_view(), name='my-connections'),
    path('network/connect/', views.ConnectionRequestView.as_view(), name='network-connect'),
    path('network/connect/<uuid:pk>/', views.ConnectionRequestView.as_view(), name='network-connect-detail'),
    path('network/disconnect/<uuid:pk>/', views.DisconnectView.as_view(), name='network-disconnect'),
]
