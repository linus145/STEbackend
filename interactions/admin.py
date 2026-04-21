from django.contrib import admin
from .models import Connection, Like, Comment

@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at', 'updated_at')
    search_fields = ('sender__email', 'receiver__email', 'sender__first_name', 'receiver__first_name')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__email', 'post__title')
    readonly_fields = ('created_at',)

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__email', 'post__title', 'content')
    readonly_fields = ('created_at',)
