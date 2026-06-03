from celery import shared_task
from django.core.mail import send_mail, get_connection
from django.conf import settings

@shared_task
def send_email_async(subject, message, recipient_list, from_email=None, html_message=None):
    """Asynchronously sends an email using Django's send_mail."""
    if from_email is None:
        from_email = settings.DEFAULT_FROM_EMAIL
    try:
        send_mail(
            subject,
            message,
            from_email,
            recipient_list,
            fail_silently=False,
            html_message=html_message,
        )
        return True
    except Exception as e:
        print(f"Celery email sending failed: {e}")
        return False


@shared_task
def send_notification_email_async(subject, message, recipient_list, from_email=None, html_message=None):
    """Asynchronously sends notification emails using dynamic settings."""
    try:
        backend = getattr(settings, "NOTIFICATION_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
        host = getattr(settings, "NOTIFICATION_EMAIL_HOST", "smtp-relay.brevo.com")
        port = int(getattr(settings, "NOTIFICATION_EMAIL_PORT", 587))
        username = getattr(settings, "NOTIFICATION_EMAIL_HOST_USER", "")
        password = getattr(settings, "NOTIFICATION_EMAIL_HOST_PASSWORD", "")
        use_tls = getattr(settings, "NOTIFICATION_EMAIL_USE_TLS", True)
        if not from_email:
            from_email = getattr(settings, "NOTIFICATION_DEFAULT_FROM_EMAIL", "lakkavaramlinus@gmail.com")
            
        connection = get_connection(
            backend=backend,
            host=host,
            port=port,
            username=username,
            password=password,
            use_tls=use_tls,
        )
        send_mail(
            subject,
            message,
            from_email,
            recipient_list,
            fail_silently=False,
            connection=connection,
            html_message=html_message,
        )
        return True
    except Exception as e:
        import logging
        logger = logging.getLogger("celery.tasks")
        logger.error(f"Celery notification email sending failed: {e}")
        return False

