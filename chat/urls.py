from django.urls import path
from .views import ChatRoomListView, Initialize1to1RoomView, MessageHistoryView, DeleteMessageView

app_name = 'chat'

urlpatterns = [
    path('rooms/', ChatRoomListView.as_view(), name='room-list'),
    path('rooms/1to1/', Initialize1to1RoomView.as_view(), name='init-1to1-room'),
    path('rooms/<uuid:room_id>/messages/', MessageHistoryView.as_view(), name='message-history'),
    path('messages/<uuid:message_id>/delete/', DeleteMessageView.as_view(), name='delete-message'),
]
