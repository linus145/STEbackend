from django.apps import AppConfig


class FollowingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "following"
    verbose_name = "Following"

    def ready(self):
        import following.signals  # noqa: F401 — register signal handlers
