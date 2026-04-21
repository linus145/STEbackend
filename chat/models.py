import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from maincore.basemodel import SoftDeleteModel

class ChatRoom(SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, blank=True, null=True, help_text="Used for group chats")
    is_group = models.BooleanField(default=False)
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='chat_rooms',
        db_index=True
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Chat Room'
        verbose_name_plural = 'Chat Rooms'
        ordering = ['-updated_at']

    def __str__(self):
        return self.name if self.name else f"Room {self.id}"

class Message(SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='messages',
        db_index=True
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='messages',
        db_index=True
    )
    text = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        ordering = ['created_at'] # Chronological ordering for chat history

    def __str__(self):
        sender_email = self.sender.email if self.sender else "System"
        return f"{sender_email} -> {self.room.id}"
