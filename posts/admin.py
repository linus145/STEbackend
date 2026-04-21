from django.contrib import admin
from .models import Post

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('id', 'author', 'created_at', 'has_media')
    list_filter = ('created_at', 'author')
    search_fields = ('content', 'author__email', 'author__first_name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('-created_at',)

    def has_media(self, obj):
        return bool(obj.media_url)
    has_media.boolean = True
    has_media.short_description = 'Media'
