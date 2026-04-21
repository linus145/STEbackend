from django.db.models.signals import post_save
from django.dispatch import receiver
from interactions.models import Connection
from .services import ChatService

@receiver(post_save, sender=Connection)
def auto_create_chat_room(sender, instance, **kwargs):
    """
    Automatically initializes a 1-to-1 chat room when a connection is accepted.
    """
    if instance.status == Connection.STATUS_ACCEPTED:
        try:
            ChatService.get_or_create_1to1_room(instance.sender, instance.receiver)
        except Exception:
            # Silent fail for signals to avoid breaking the connection flow
            pass
