from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.first_name', read_only=True)
    
    class Meta:
        model = Notification
        fields = (
            'id', 'sender_name', 'notification_type', 
            'post_id', 'message', 'is_read', 'created_at'
        )
        read_only_fields = ('id', 'created_at')
