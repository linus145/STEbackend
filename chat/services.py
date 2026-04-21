from django.db import transaction
from django.db.models import Prefetch, Count
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from .models import ChatRoom, Message
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

class ChatService:
    @staticmethod
    def get_user_rooms(user: User):
        """
        Retrieves all chat rooms a user is part of, optimized with the latest message.
        """
        return ChatRoom.objects.filter(participants=user).prefetch_related(
            'participants',
            Prefetch('messages', queryset=Message.objects.order_by('-created_at'))
        ).order_by('-updated_at')

    @staticmethod
    def get_or_create_1to1_room(user1: User, user2: User) -> ChatRoom:
        """
        Retrieves or safely creates a 1-to-1 chat room between two users.
        """
        if user1 == user2:
            raise ValueError("Users cannot create a chat room with themselves.")

        # Natively check if an exact 1-to-1 room exists using aggregation
        rooms = ChatRoom.objects.filter(is_group=False).annotate(p_count=Count('participants')).filter(p_count=2)
        rooms = rooms.filter(participants=user1).filter(participants=user2)
        
        if rooms.exists():
            return rooms.first()

        # If it doesn't exist, utilize atomicity to safely create
        with transaction.atomic():
            room = ChatRoom.objects.create(is_group=False)
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
            room = ChatRoom.objects.get(id=room_id, participants=user)
        except ChatRoom.DoesNotExist:
            return None
        return Message.objects.filter(room=room).select_related('sender').order_by('created_at')

    @staticmethod
    def save_message(room_id: str, sender_id: str, text: str) -> Message:
        """
        Primary engine for Django Channels. Saves an arriving websocket message directly.
        """
        try:
            room = ChatRoom.objects.get(id=room_id)
            sender = User.objects.get(id=sender_id)
            
            # Create message within transaction to trigger room updated_at implicitly by hand
            with transaction.atomic():
                msg = Message.objects.create(room=room, sender=sender, text=text)
                room.save() # bump the `updated_at` automatically handling sort by recent
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
            message.delete() # Inherits SoftDeleteModel's delete
            return True
        except Message.DoesNotExist:
            return False
