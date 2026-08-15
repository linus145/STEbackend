from django.db import models
from rest_framework import status, generics, permissions
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth import get_user_model

from .serializers import (
    CommentSerializer,
    CommentCreateSerializer,
    ConnectionSerializer,
)
from .models import Connection
from .services import InteractionService
from useraccounts.serializers import UserSerializer

User = get_user_model()


from maincore.pagination import StandardResultsSetPagination


class ToggleLikeView(APIView):
    """
    Toggles a like on a post for the authenticated user.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        post_id = request.data.get("post_id")
        if not post_id:
            return Response(
                {"error": "post_id is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        result = InteractionService.toggle_like(request.user, post_id)
        if "error" in result:
            return Response(result, status=status.HTTP_404_NOT_FOUND)

        return Response(result, status=status.HTTP_200_OK)


class CommentListCreateView(generics.ListAPIView):
    """
    Returns comments for a specific post_id via query param or creates a new one.
    """

    pagination_class = StandardResultsSetPagination

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CommentCreateSerializer
        return CommentSerializer

    def get_queryset(self):
        post_id = self.request.query_params.get("post_id")
        if not post_id:
            return []
        return InteractionService.get_comments_for_post(post_id)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer_class()(data=request.data)
        if serializer.is_valid():
            comment = InteractionService.add_comment(
                request.user, serializer.validated_data
            )
            return Response(
                CommentSerializer(comment).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CommentDeleteView(APIView):
    permission_classes = (IsAuthenticated,)

    def delete(self, request, comment_id, *args, **kwargs):
        success = InteractionService.delete_comment(request.user, comment_id)
        if success:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {"error": "Comment not found or unauthorized."},
            status=status.HTTP_403_FORBIDDEN,
        )


class NetworkPeopleView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        role = self.request.query_params.get("role", "FOUNDER")
        return User.objects.filter(role=role).exclude(id=self.request.user.id).select_related('founder_profile', 'investor_profile')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        
        # Get connections for the current user to inject status efficiently
        connections = Connection.objects.filter(
            models.Q(sender=request.user) | models.Q(receiver=request.user)
        ).exclude(status__in=[Connection.STATUS_REJECTED, Connection.STATUS_DISCONNECTED])
        
        connection_map = {
            str(conn.receiver_id if conn.sender_id == request.user.id else conn.sender_id): {
                "id": str(conn.id),
                "status": conn.status,
                "is_incoming": conn.receiver_id == request.user.id,
            } for conn in connections
        }

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            for user_data in serializer.data:
                user_data["connection_info"] = connection_map.get(str(user_data["id"]))
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        for user_data in serializer.data:
            user_data["connection_info"] = connection_map.get(str(user_data["id"]))
        return Response(serializer.data)


class MyConnectionsView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        # Fetch ONLY ACCEPTED connections for "My Connections"
        connections = Connection.objects.filter(
            (models.Q(sender=self.request.user) | models.Q(receiver=self.request.user)),
            status=Connection.STATUS_ACCEPTED
        ).select_related('sender', 'receiver', 'sender__founder_profile', 'receiver__founder_profile')
        
        # This is a bit tricky with pagination if we want to return Users instead of Connections
        # Let's return the Users directly using a subquery or filtered queryset
        user_ids = Connection.objects.filter(
            (models.Q(sender=self.request.user) | models.Q(receiver=self.request.user)),
            status=Connection.STATUS_ACCEPTED
        ).values_list('sender_id', 'receiver_id')
        
        flat_ids = set()
        for s_id, r_id in user_ids:
            if s_id != self.request.user.id: flat_ids.add(s_id)
            if r_id != self.request.user.id: flat_ids.add(r_id)
            
        return User.objects.filter(id__in=flat_ids).select_related('founder_profile', 'investor_profile')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        
        # Map connection info for injection
        connections = Connection.objects.filter(
            (models.Q(sender=request.user) | models.Q(receiver=request.user)),
            status=Connection.STATUS_ACCEPTED
        )
        connection_map = {
            str(conn.sender_id if conn.receiver_id == request.user.id else conn.receiver_id): {
                "id": str(conn.id),
                "status": conn.status,
                "is_incoming": conn.receiver_id == request.user.id,
                "sender_id": str(conn.sender_id),
            } for conn in connections
        }

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            for user_data in serializer.data:
                user_data["connection_info"] = connection_map.get(str(user_data["id"]))
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        for user_data in serializer.data:
            user_data["connection_info"] = connection_map.get(str(user_data["id"]))
        return Response(serializer.data)


class InvitationsView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        # Fetch users who sent PENDING connection requests
        return User.objects.filter(
            sent_connections__receiver=self.request.user,
            sent_connections__status=Connection.STATUS_PENDING
        ).select_related('founder_profile', 'investor_profile')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        
        # Get connection details for injection
        connections = Connection.objects.filter(
            receiver=request.user,
            status=Connection.STATUS_PENDING
        )
        connection_map = {
            str(conn.sender_id): {
                "id": str(conn.id),
                "status": conn.status,
                "is_incoming": True,
                "sender_id": str(conn.sender_id),
                "created_at": conn.created_at
            } for conn in connections
        }

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            for user_data in serializer.data:
                user_data["connection_info"] = connection_map.get(str(user_data["id"]))
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        for user_data in serializer.data:
            user_data["connection_info"] = connection_map.get(str(user_data["id"]))
        return Response(serializer.data)


class PendingSentRequestsView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        # Fetch users to whom current user sent PENDING connection requests
        return User.objects.filter(
            received_connections__sender=self.request.user,
            received_connections__status=Connection.STATUS_PENDING
        ).select_related('founder_profile', 'investor_profile')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        
        connections = Connection.objects.filter(
            sender=request.user,
            status=Connection.STATUS_PENDING
        )
        connection_map = {
            str(conn.receiver_id): {
                "id": str(conn.id),
                "status": conn.status,
                "is_incoming": False,
                "sender_id": str(conn.sender_id),
                "created_at": conn.created_at
            } for conn in connections
        }

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            for user_data in serializer.data:
                user_data["connection_info"] = connection_map.get(str(user_data["id"]))
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        for user_data in serializer.data:
            user_data["connection_info"] = connection_map.get(str(user_data["id"]))
        return Response(serializer.data)


class DisconnectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        try:
            # pk is either the target user's ID or the connection ID
            connection = Connection.objects.filter(
                (
                    models.Q(sender=request.user, receiver_id=pk)
                    | models.Q(sender_id=pk, receiver=request.user)
                    | models.Q(id=pk, sender=request.user)
                    | models.Q(id=pk, receiver=request.user)
                )
            ).first()

            if not connection:
                return Response(
                    {"error": "Connection not found"}, status=status.HTTP_404_NOT_FOUND
                )

            # Update status instead of hard/soft deleting the connection object
            connection.status = Connection.STATUS_DISCONNECTED
            connection.save()

            # Deactivate the associated 1-to-1 chat room
            from chat.models import ChatRoom, Message
            from django.db.models import Count
            
            # Find rooms linked to this connection OR matching these participants (legacy fallback)
            rooms = ChatRoom.objects.filter(
                models.Q(connection=connection) | 
                (models.Q(is_group=False) & models.Q(participants=request.user) & models.Q(participants__id=pk))
            ).annotate(p_count=Count('participants')).filter(p_count=2, is_active=True)

            for room in rooms:
                room.is_active = False
                room.save()
                # Ensure messages are soft-deleted as well
                Message.objects.filter(room=room).delete()

            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ConnectionRequestView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        receiver_id = request.data.get("receiver_id")
        if not receiver_id:
            return Response(
                {"error": "receiver_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        if str(receiver_id) == str(request.user.id):
            return Response(
                {"error": "You cannot connect to yourself"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            receiver = User.objects.get(id=receiver_id)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Check for existing connection in either direction (sender->receiver or receiver->sender)
        # Using all_objects to include soft-deleted records
        from django.db.models import Q

        connection = Connection.all_objects.filter(
            (
                Q(sender=request.user, receiver=receiver)
                | Q(sender=receiver, receiver=request.user)
            )
        ).first()

        if connection:
            if connection.is_deleted or connection.status in [Connection.STATUS_DISCONNECTED, Connection.STATUS_REJECTED]:
                # Restore or reset the connection for a new request
                if connection.is_deleted:
                    connection.restore()
                connection.status = Connection.STATUS_PENDING
                connection.sender = request.user
                connection.receiver = receiver
                connection.save()
                return Response(
                    ConnectionSerializer(connection).data,
                    status=status.HTTP_201_CREATED,
                )

            return Response(
                {
                    "message": "Connection already exists or is pending",
                    "status": connection.status,
                    "is_sender": connection.sender == request.user,
                },
                status=status.HTTP_200_OK,
            )

        # Create new connection
        connection = Connection.objects.create(sender=request.user, receiver=receiver)

        return Response(
            ConnectionSerializer(connection).data, status=status.HTTP_201_CREATED
        )

    def patch(self, request, pk):
        try:
            connection = Connection.objects.get(pk=pk, receiver=request.user)
        except Connection.DoesNotExist:
            return Response(
                {"error": "Connection request not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        new_status = request.data.get("status")
        if new_status not in [Connection.STATUS_ACCEPTED, Connection.STATUS_REJECTED]:
            return Response(
                {"error": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST
            )

        connection.status = new_status
        connection.save()

        if new_status == Connection.STATUS_ACCEPTED:
            from chat.services import ChatService
            ChatService.get_or_create_1to1_room(connection.sender, connection.receiver)

        return Response(ConnectionSerializer(connection).data)
