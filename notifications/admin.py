from django.contrib import admin
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('recipient', 'sender', 'notification_type', 'is_read', 'created_at', 'is_deleted')
    list_filter = ('notification_type', 'is_read', 'created_at', 'is_deleted')
    search_fields = ('recipient__email', 'sender__email', 'message')
    readonly_fields = ('id', 'created_at')
    ordering = ('-created_at',)
