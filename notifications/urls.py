from django.urls import path
from notifications.views import (
    NotificationListView, 
    MarkNotificationReadView, 
    MarkAllReadView, 
    DeleteAllNotificationsView,
    NotificationUnreadCountsView
)

urlpatterns = [
    path('', NotificationListView.as_view(), name='notification-list'),
    path('user/', NotificationListView.as_view(dashboard_filter='USER'), name='notification-user-list'),
    path('recruiter/', NotificationListView.as_view(dashboard_filter='RECRUITER'), name='notification-recruiter-list'),
    path('interview/', NotificationListView.as_view(dashboard_filter='INTERVIEW'), name='notification-interview-list'),
    path('hr/', NotificationListView.as_view(dashboard_filter='HR'), name='notification-hr-list'),
    path('counts/', NotificationUnreadCountsView.as_view(), name='notification-counts'),
    path('<uuid:pk>/read/', MarkNotificationReadView.as_view(), name='mark-read'),
    path('mark-all-read/', MarkAllReadView.as_view(), name='mark-all-read'),
    path('delete-all/', DeleteAllNotificationsView.as_view(), name='delete-all'),
]
