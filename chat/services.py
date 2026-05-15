from django.db import transaction, models
from django.db.models import Prefetch, Count
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from .models import ChatRoom, Message
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class ChatService:
    @staticmethod
    def get_user_rooms(user: User, room_type: str = None):
        """
        Retrieves all active chat rooms a user is part of.
        Filters:
          - 'connection': only connection-based rooms
          - 'direct': only direct/HR rooms
          - 'personal': connection rooms + direct rooms ONLY if user has no company
                        (company owners see direct rooms in recruiter dashboard instead)
          - None: all rooms
        """
        from interactions.models import Connection

        qs = (
            ChatRoom.objects.filter(participants=user, is_active=True)
            .filter(
                models.Q(is_group=True)
                | models.Q(connection__status=Connection.STATUS_ACCEPTED)
                | models.Q(connection__isnull=True)
            )
            .distinct()
        )

        if room_type == "personal":
            # If user owns a company, exclude direct/HR rooms (they go to recruiter dashboard)
            has_company = (
                hasattr(user, "company_profile") and user.company_profile is not None
            )
            if has_company:
                qs = qs.exclude(room_type=ChatRoom.ROOM_TYPE_DIRECT)
        elif room_type:
            qs = qs.filter(room_type=room_type)

        return qs.prefetch_related(
            "participants",
            Prefetch("messages", queryset=Message.objects.order_by("-created_at")),
        ).order_by("-updated_at")

    @staticmethod
    def get_or_create_1to1_room(user1: User, user2: User) -> ChatRoom:
        """
        Retrieves or safely creates a 1-to-1 chat room between two users.
        Ensures a fresh chat is created based on the CURRENT ACTIVE connection.
        """
        from interactions.models import Connection

        if user1 == user2:
            raise ValueError("Users cannot create a chat room with themselves.")

        # Find the active connection between these users
        connection = Connection.objects.filter(
            (
                models.Q(sender=user1, receiver=user2)
                | models.Q(sender=user2, receiver=user1)
            ),
            status=Connection.STATUS_ACCEPTED,
        ).first()

        if not connection:
            raise ValueError("No active connection found between these users.")

        # Check for an active room linked to this specific connection
        room = ChatRoom.objects.filter(connection=connection, is_active=True).first()

        if room:
            return room

        # If no active room exists for this connection, create a NEW one
        with transaction.atomic():
            room = ChatRoom.objects.create(
                connection=connection,
                is_group=False,
                room_type=ChatRoom.ROOM_TYPE_CONNECTION,
            )
            room.participants.add(user1, user2)
        return room

    @staticmethod
    def create_group_room(creator: User, name: str, participant_ids: list) -> ChatRoom:
        """
        Creates a new group room.
        """
        with transaction.atomic():
            room = ChatRoom.objects.create(name=name, is_group=True)
            room.participants.add(creator)
            valid_users = User.objects.filter(id__in=participant_ids)
            room.participants.add(*valid_users)
        return room

    @staticmethod
    def get_room_messages(room_id: str, user: User):
        """
        Retrieves message history. Checks if user is permitted safely.
        """
        try:
            room = ChatRoom.objects.get(id=room_id, participants=user, is_active=True)
        except ChatRoom.DoesNotExist:
            return None
        return (
            Message.objects.filter(room=room)
            .select_related("sender")
            .order_by("created_at")
        )

    @staticmethod
    def save_message(room_id: str, sender_id: str, text: str) -> Message:
        """
        Primary engine for Django Channels. Saves an arriving websocket message directly.
        Validates that the room is active and connection is accepted.
        """
        try:
            room = ChatRoom.objects.get(id=room_id, is_active=True)

            # If it's a 1-to-1 room, check the connection status
            if not room.is_group and room.connection:
                if room.connection.status != room.connection.STATUS_ACCEPTED:
                    logger.error(
                        f"Chat save_message blocked: Connection {room.connection.id} is not ACCEPTED."
                    )
                    return None

            sender = User.objects.get(id=sender_id)

            # Create message within transaction to trigger room updated_at implicitly by hand
            with transaction.atomic():
                msg = Message.objects.create(room=room, sender=sender, text=text)
                room.save()  # bump the `updated_at` automatically handling sort by recent
            return msg
        except (ChatRoom.DoesNotExist, User.DoesNotExist) as e:
            logger.error(f"Chat save_message Failed: {e}")
            return None

    @staticmethod
    def delete_message(message_id: str, user: User) -> bool:
        """
        Soft deletes a message if the requester is the sender.
        """
        try:
            message = Message.objects.get(id=message_id, sender=user)
            message.delete()  # Inherits SoftDeleteModel's delete
            return True
        except Message.DoesNotExist:
            return False
