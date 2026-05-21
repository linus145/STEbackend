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
    page = models.OneToOneField(Page, on_delete=models.CASCADE, related_name='seo')
    meta_title = models.CharField(max_length=255)
    meta_description = models.TextField()
    meta_keywords = models.CharField(max_length=255, blank=True, null=True, help_text="Comma-separated keywords")
    
    # OpenGraph (Social Media)
    og_title = models.CharField(max_length=255, blank=True, null=True)
    og_description = models.TextField(blank=True, null=True)
    og_image = models.URLField(blank=True, null=True, help_text="URL of the OpenGraph image")
    og_type = models.CharField(max_length=50, default='website')

    class Meta:
        verbose_name = "Page SEO"
        verbose_name_plural = "Page SEO Settings"

    def __str__(self):
        return f"SEO for {self.page.name}"
