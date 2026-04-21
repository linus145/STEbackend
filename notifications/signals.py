from django.db.models.signals import post_save
from django.dispatch import receiver
from interactions.models import Like, Connection
from comments.models import Comment
from .models import Notification

@receiver(post_save, sender=Like)
def create_like_notification(sender, instance, created, **kwargs):
    if created:
        # Don't notify if user likes their own post
        if instance.user != instance.post.author:
            Notification.objects.create(
                recipient=instance.post.author,
                sender=instance.user,
                notification_type='LIKE',
                post_id=instance.post.id,
                message=f"{instance.user.first_name} liked your post."
            )

@receiver(post_save, sender=Comment)
def create_comment_notification(sender, instance, created, **kwargs):
    if created:
        if instance.user != instance.post.author:
            Notification.objects.create(
                recipient=instance.post.author,
                sender=instance.user,
                notification_type='COMMENT',
                post_id=instance.post.id,
                message=f"{instance.user.first_name} commented on your post."
            )

@receiver(post_save, sender=Connection)
def create_connection_notification(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            recipient=instance.receiver,
            sender=instance.sender,
            notification_type='CONNECTION_REQUEST',
            message=f"{instance.sender.first_name} sent you a connection request."
        )
    else:
        # Check if status was changed to ACCEPTED
        if instance.status == 'ACCEPTED':
            # Check if notification already exists to avoid duplicates on multiple saves
            if not Notification.objects.filter(
                recipient=instance.sender,
                sender=instance.receiver,
                notification_type='CONNECTION_ACCEPTED'
            ).exists():
                Notification.objects.create(
                    recipient=instance.sender,
                    sender=instance.receiver,
                    notification_type='CONNECTION_ACCEPTED',
                    message=f"{instance.receiver.first_name} accepted your connection request."
                )
        elif instance.status == 'REJECTED':
             # Notify the sender that their request was rejected (optional but requested)
             if not Notification.objects.filter(
                recipient=instance.sender,
                sender=instance.receiver,
                notification_type='CONNECTION_REJECTED'
            ).exists():
                Notification.objects.create(
                    recipient=instance.sender,
                    sender=instance.receiver,
                    notification_type='CONNECTION_REJECTED',
                    message=f"{instance.receiver.first_name} declined your connection request."
                )
