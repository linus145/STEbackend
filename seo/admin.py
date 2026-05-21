from django.contrib import admin
from django.db import models
from django.forms import Textarea
from .models import Page, PageSEO

class PageSEOInline(admin.StackedInline):
    model = PageSEO
    can_delete = False
    verbose_name = "SEO Meta Setting"
    verbose_name_plural = "SEO Meta Settings"
    formfield_overrides = {
        models.TextField: {
            'widget': Textarea(
                attrs={
                    'rows': 4,
                    'cols': 60,
                    'style': 'font-family: monospace; font-size: 13px; padding: 6px; width: 100%; max-width: 600px; border-radius: 4px;'
                }
            )
        },
    }

@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ('name', 'url_path', 'get_meta_title')
    search_fields = ('name', 'url_path', 'seo__meta_title')
    inlines = [PageSEOInline]

    def get_meta_title(self, obj):
        try:
            return obj.seo.meta_title
        except PageSEO.DoesNotExist:
            return "-"
    get_meta_title.short_description = 'Meta Title'
