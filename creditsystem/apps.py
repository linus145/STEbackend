from django.apps import AppConfig


class CreditsystemConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'creditsystem'

    def ready(self):
        import creditsystem.signals

