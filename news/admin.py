from django.contrib import admin
from .models import News

@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_editable = ('is_deleted',)
    list_display = ('title','short_title', 'author', 'is_popular', 'is_trending', 'is_top_news', 'created_at', 'is_deleted')
    list_filter = ('is_popular', 'is_trending', 'is_top_news', 'created_at', 'is_deleted')
    search_fields = ('title', 'content', 'author__email')
    ordering = ('-created_at',)
    
    fieldsets = (
        (None, {
            'fields': ('title', 'short_title', 'author', 'content', 'media_url')
        }),
        ('Status Flags (Administrative)', {
            'fields': ('is_popular', 'is_trending', 'is_top_news'),
            'description': 'These flags control the appearance of the article in special news sections.'
        }),
    )
