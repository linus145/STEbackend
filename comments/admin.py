from django.contrib import admin
from .models import Comment

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'short_content', 'created_at')
    list_filter = ('created_at', 'user')
    search_fields = ('content', 'user__email', 'post__id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('-created_at',)

    def short_content(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    short_content.short_description = 'Content'
