from django.contrib import admin
from .models import ChatRoom, Message

@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_group', 'created_at', 'updated_at')
    list_filter = ('is_group', 'created_at')
    search_fields = ('id', 'name', 'participants__email')
    filter_horizontal = ('participants',)
    readonly_fields = ('id', 'created_at', 'updated_at')

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'room', 'sender', 'text_snippet', 'created_at')
    list_filter = ('created_at', 'room')
    search_fields = ('text', 'sender__email', 'room__id')
    readonly_fields = ('id', 'created_at')

    def text_snippet(self, obj):
        return obj.text[:50] + "..." if len(obj.text) > 50 else obj.text
    text_snippet.short_description = 'Message Content'
