from rest_framework import serializers
from .models import ChatRoom, Message

from useraccounts.serializers import UserSerializer

class MessageSerializer(serializers.ModelSerializer):
    sender_data = UserSerializer(source='sender', read_only=True)

    class Meta:
        model = Message
        fields = ('id', 'room', 'sender', 'sender_data', 'text', 'is_read', 'created_at')
        read_only_fields = ('id', 'sender', 'created_at')

class ChatRoomSerializer(serializers.ModelSerializer):
    latest_message = serializers.SerializerMethodField()
    participants_data = UserSerializer(source='participants', many=True, read_only=True)

    class Meta:
        model = ChatRoom
        fields = ('id', 'name', 'is_group', 'participants_data', 'latest_message', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_latest_message(self, obj):
        # We assume the service layer optimizes the query, but as a fallback:
        # A prefetch wrapper on `messages` makes this cheap.
        msg = obj.messages.order_by('-created_at').first()
        if msg:
            return {
                "id": str(msg.id),
                "text": msg.text,
                "sender_id": str(msg.sender.id) if msg.sender else None,
                "sender_email": msg.sender.email if msg.sender else "System",
                "created_at": msg.created_at.isoformat()
            }
        return None
