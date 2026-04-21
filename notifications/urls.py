from django.urls import path
from .views import NotificationListView, MarkNotificationReadView, MarkAllReadView, DeleteAllNotificationsView

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('<uuid:pk>/read/', MarkNotificationReadView.as_view(), name='mark-read'),
    path('mark-all-read/', MarkAllReadView.as_view(), name='mark-all-read'),
    path('delete-all/', DeleteAllNotificationsView.as_view(), name='delete-all'),
]
