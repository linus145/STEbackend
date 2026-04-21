import uuid
from django.db import models
from django.conf import settings
from maincore.basemodel import SoftDeleteModel

class Notification(SoftDeleteModel):
    NOTIFICATION_TYPES = (
        ('LIKE', 'Like'),
        ('COMMENT', 'Comment'),
        ('CONNECTION_REQUEST', 'Connection Request'),
        ('CONNECTION_ACCEPTED', 'Connection Accepted'),
        ('CONNECTION_REJECTED', 'Connection Rejected'),
        ('SYSTEM', 'System'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_notifications',
        null=True,
        blank=True
    )
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    post_id = models.UUIDField(null=True, blank=True) # ID of the post related to the notification
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.recipient.email}: {self.notification_type}"
