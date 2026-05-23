from django.contrib import admin
from django import forms
from django.db import models
from .models import Page, PageSEO

class PageSEOForm(forms.ModelForm):
    class Meta:
        model = PageSEO
        fields = '__all__'
        widgets = {
            'meta_title': forms.TextInput(attrs={
                'style': 'width: 100%; max-width: 600px; padding: 6px;',
                'placeholder': 'Ideal length: 50-60 characters.'
            }),
            'meta_description': forms.Textarea(attrs={
                'rows': 4,
                'cols': 60,
                'style': 'font-family: monospace; font-size: 13px; padding: 6px; width: 100%; max-width: 600px; border-radius: 4px;',
                'placeholder': 'Ideal length: 150-160 characters.'
            }),
        }

    def clean_meta_title(self):
        title = self.cleaned_data.get('meta_title')
        if len(title) > 60:
            # We add a non-blocking warning check or standard validation
            pass
        return title

class PageSEOInline(admin.StackedInline):
    model = PageSEO
    form = PageSEOForm
    can_delete = False
    verbose_name = "SEO Meta Setting"
    verbose_name_plural = "SEO Meta Settings"
    fieldsets = (
        ('Global Page Settings', {
            'fields': ('page_type', 'is_noindex', 'is_nofollow')
        }),
        ('Standard SEO Tags', {
            'fields': ('meta_title', 'meta_description', 'meta_keywords')
        }),
        ('OpenGraph Social Sharing Tags', {
            'fields': ('og_title', 'og_description', 'og_image', 'og_type'),
            'classes': ('collapse',)
        }),
    )

@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ('name', 'url_path', 'get_page_type', 'get_meta_title', 'get_index_status')
    search_fields = ('name', 'url_path', 'seo__meta_title')
    inlines = [PageSEOInline]

    def get_meta_title(self, obj):
        try:
            return obj.seo.meta_title
        except PageSEO.DoesNotExist:
            return "-"
    get_meta_title.short_description = 'Meta Title'

    def get_page_type(self, obj):
        try:
            return obj.seo.get_page_type_display()
        except PageSEO.DoesNotExist:
            return "-"
    get_page_type.short_description = 'Page Type'

    def get_index_status(self, obj):
        try:
            seo = obj.seo
            status_parts = []
            if seo.is_noindex:
                status_parts.append('noindex')
            else:
                status_parts.append('index')
            if seo.is_nofollow:
                status_parts.append('nofollow')
            else:
                status_parts.append('follow')
            return ", ".join(status_parts)
        except PageSEO.DoesNotExist:
            return "-"
    get_index_status.short_description = 'Robots Directives'

