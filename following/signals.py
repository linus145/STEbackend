from django.db.models.signals import post_save
from django.dispatch import receiver

from interactions.models import Connection
from .models import Follow


@receiver(post_save, sender=Connection)
def auto_follow_on_connection_accept(sender, instance, **kwargs):
    """
    Auto-follow both users when a connection is accepted (LinkedIn-style).
    This keeps all follow logic inside the `following` app.
    """
    if instance.status == Connection.STATUS_ACCEPTED:
        Follow.objects.get_or_create(
            follower=instance.sender,
            following=instance.receiver,
        )
        Follow.objects.get_or_create(
            follower=instance.receiver,
            following=instance.sender,
        )
