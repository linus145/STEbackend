from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth import get_user_model

from .serializers import ChatRoomSerializer, MessageSerializer
from .services import ChatService

User = get_user_model()

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200

class ChatRoomListView(generics.ListAPIView):
    """
    Retrieves all chat rooms for the logged in user along with metadata.
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = ChatRoomSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return ChatService.get_user_rooms(self.request.user)

class Initialize1to1RoomView(APIView):
    """
    Fetches an existing 1to1 room or instantiates one between users cleanly.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        target_user_id = request.data.get('target_user_id')
        if not target_user_id:
            return Response({'error': 'target_user_id is strictly required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Check if they are connected
        from interactions.models import Connection
        from django.db.models import Q
        is_connected = Connection.objects.filter(
            (Q(sender=request.user, receiver=target_user) | Q(sender=target_user, receiver=request.user)),
            status=Connection.STATUS_ACCEPTED
        ).exists()

        if not is_connected:
            return Response({'error': 'You can only message connected partners.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            room = ChatService.get_or_create_1to1_room(request.user, target_user)
            serializer = ChatRoomSerializer(room)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class MessageHistoryView(generics.ListAPIView):
    """
    Fetches paginated chronological messages for a specific room.
    """
    permission_classes = (IsAuthenticated,)
    serializer_class = MessageSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        room_id = self.kwargs.get('room_id')
        qs = ChatService.get_room_messages(room_id, self.request.user)
        if qs is None:
            return [] # or handle 404 cleanly via exception overriding
        return qs
class DeleteMessageView(APIView):
    """
    Deletes a specific message. Only permitted for the sender.
    """
    permission_classes = (IsAuthenticated,)

    def delete(self, request, message_id, *args, **kwargs):
        success = ChatService.delete_message(message_id, request.user)
        if success:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {'error': 'Message not found or authorization denied.'}, 
            status=status.HTTP_404_NOT_FOUND
        )
