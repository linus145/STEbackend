from django.db import models

class AboutUs(models.Model):
    title = models.CharField(max_length=255, default="Architecting the future of Startup Ecosystems.")
    description = models.TextField()
    mission_statement = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "About Us"

    def __str__(self):
        return self.title

class MissionPrinciple(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=50)  # Emoji or icon name
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title

class Blog(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    excerpt = models.TextField()
    content = models.TextField(blank=True, null=True)
    author = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    date = models.DateField()
    image = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class JobOpening(models.Model):
    role = models.CharField(max_length=255)
    department = models.CharField(max_length=100)
    location = models.CharField(max_length=100)
    job_type = models.CharField(max_length=50)  # e.g. Full-time, Remote
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.role

class ContactInquiry(models.Model):
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    subject = models.CharField(max_length=255)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Contact Inquiries"

    def __str__(self):
        return f"{self.full_name} - {self.subject}"


class ContactSales(models.Model):
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    company_name = models.CharField(max_length=255)
    company_size = models.CharField(max_length=50)
    phone_number = models.CharField(max_length=50, blank=True, null=True)
    message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Contact Sales Inquiries"

    def __str__(self):
        return f"{self.full_name} - {self.company_name}"


class Careers(models.Model):
    role = models.CharField(max_length=255)
    department = models.CharField(max_length=100)
    location = models.CharField(max_length=100)
    job_type = models.CharField(max_length=50)  # e.g. Full-time, Remote
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Careers"

    def __str__(self):
        return self.role

