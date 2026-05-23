from django.db import models

class Page(models.Model):
    name = models.CharField(max_length=255, help_text="Human readable name of the page (e.g. Home, About Us)")
    url_path = models.CharField(max_length=255, unique=True, help_text="The URL path or unique key of the page (e.g. '/', '/aboutus', '/blogs', '/blogs/my-first-post')")
    
    class Meta:
        verbose_name = "Page"
        verbose_name_plural = "Pages"

    def __str__(self):
        return self.name

class PageSEO(models.Model):
    PAGE_TYPE_CHOICES = [
        ('HOME', 'Home Page'),
        ('ABOUT', 'About Us Page'),
        ('PRICING', 'Pricing Page'),
        ('BLOG', 'Blogs List Page'),
        ('ARTICLE', 'Blog Article'),
        ('CAREERS', 'Careers Page'),
        ('CONTACT', 'Contact/Demo Page'),
    ]

    page = models.OneToOneField(Page, on_delete=models.CASCADE, related_name='seo')
    page_type = models.CharField(max_length=20, choices=PAGE_TYPE_CHOICES, default='HOME')
    meta_title = models.CharField(max_length=255)
    meta_description = models.TextField()
    meta_keywords = models.CharField(max_length=255, blank=True, null=True, help_text="Comma-separated keywords")
    
    # Robots Directives
    is_noindex = models.BooleanField(default=False, help_text="Instruct search engines not to index this page")
    is_nofollow = models.BooleanField(default=False, help_text="Instruct search engines not to follow links on this page")
    
    # OpenGraph (Social Media)
    og_title = models.CharField(max_length=255, blank=True, null=True)
    og_description = models.TextField(blank=True, null=True)
    og_image = models.URLField(blank=True, null=True, help_text="URL of the OpenGraph image")
    og_type = models.CharField(max_length=50, default='website')

    class Meta:
        verbose_name = "Page SEO"
        verbose_name_plural = "Page SEO Settings"

    def __str__(self):
        return f"SEO for {self.page.name} ({self.get_page_type_display()})"


from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache

@receiver(post_save, sender=Page)
@receiver(post_delete, sender=Page)
def clear_page_cache(sender, instance, **kwargs):
    """Bust cache when Page is updated/deleted"""
    try:
        from .views import normalize_url_path
        normalized = normalize_url_path(instance.url_path)
        cache.delete(f"seo_page_path:{normalized}")
        if normalized.startswith('/blogs/'):
            cache.delete("seo_page_path:/blogs")
    except Exception:
        pass

@receiver(post_save, sender=PageSEO)
@receiver(post_delete, sender=PageSEO)
def clear_pageseo_cache(sender, instance, **kwargs):
    """Bust cache when PageSEO configuration is updated/deleted"""
    try:
        if instance.page:
            from .views import normalize_url_path
            normalized = normalize_url_path(instance.page.url_path)
            cache.delete(f"seo_page_path:{normalized}")
            if normalized.startswith('/blogs/'):
                cache.delete("seo_page_path:/blogs")
    except Exception:
        pass


