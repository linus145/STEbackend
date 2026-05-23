from celery import shared_task
from django.core.mail import send_mail
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
