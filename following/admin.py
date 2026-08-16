from django.contrib import admin
from .models import Follow, CompanyFollow


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ("follower", "following", "created_at")
    list_filter = ("created_at",)
    search_fields = ("follower__email", "following__email")
    raw_id_fields = ("follower", "following")
    readonly_fields = ("id", "created_at")


@admin.register(CompanyFollow)
class CompanyFollowAdmin(admin.ModelAdmin):
    list_display = ("follower", "company", "created_at")
    list_filter = ("created_at",)
    search_fields = ("follower__email", "company__company_name")
    raw_id_fields = ("follower", "company")
    readonly_fields = ("id", "created_at")
