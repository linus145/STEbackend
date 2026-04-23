from django.db import models
from rest_framework import status, generics, permissions
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


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


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


class NetworkPeopleView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        role = request.query_params.get("role", "FOUNDER")

        # Start with a base queryset excluding the current user immediately
        base_qs = User.objects.filter(role=role).exclude(id=request.user.id)

        # Optionally exclude people I'm already connected with or have a pending request with
        exclude_existing = (
            request.query_params.get("exclude_existing", "false") == "true"
        )
        if exclude_existing:
            # Find all users I have a PENDING or ACCEPTED connection with
            # We use .objects (not all_objects) so COMPLETED/DELETED connections are gone from this list
            # and we specifically exclude REJECTED so they become discoverable again.
            active_connections = Connection.objects.filter(
                models.Q(sender=request.user) | models.Q(receiver=request.user)
            ).exclude(status=Connection.STATUS_REJECTED)

            # Flatten and get unique IDs
            exclude_ids = {request.user.id}  # Always exclude self
            for conn in active_connections:
                exclude_ids.add(conn.sender_id)
                exclude_ids.add(conn.receiver_id)

            base_qs = base_qs.exclude(id__in=exclude_ids)

        serializer = UserSerializer(base_qs, many=True)
        return Response(serializer.data)


class MyConnectionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Fetch connections using the default manager (excludes DELETED)
        connections = Connection.objects.filter(
            (models.Q(sender=request.user) | models.Q(receiver=request.user))
        ).exclude(status=Connection.STATUS_REJECTED)

        results = []
        seen_user_ids = set()

        for conn in connections:
            other_user = conn.receiver if conn.sender == request.user else conn.sender
            if other_user.id != request.user.id and other_user.id not in seen_user_ids:
                user_data = UserSerializer(other_user).data
                # Inject connection metadata for the frontend
                user_data["connection_info"] = {
                    "id": str(conn.id),
                    "status": conn.status,
                    "is_incoming": conn.receiver == request.user,
                    "sender_id": str(conn.sender.id),
                }
                results.append(user_data)
                seen_user_ids.add(other_user.id)

        return Response(results)


class DisconnectView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        try:
            # pk is the other user's ID
            connection = Connection.objects.filter(
                (
                    models.Q(sender=request.user, receiver_id=pk)
                    | models.Q(sender_id=pk, receiver=request.user)
                )
            ).first()

            if not connection:
                return Response(
                    {"error": "Connection not found"}, status=status.HTTP_404_NOT_FOUND
                )

            connection.delete()
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
            if connection.is_deleted:
                # Restore the soft-deleted connection
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
        return Response(ConnectionSerializer(connection).data)
