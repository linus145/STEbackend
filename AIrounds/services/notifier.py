from django.core.mail import send_mail, get_connection
from django.conf import settings
from django.template.loader import render_to_string
from notifications.models import Notification
import logging

logger = logging.getLogger("ai_rounds.notifier")


class InterviewNotifier:
    """Handles communications related to the AI interview process."""

    @staticmethod
    def notify_candidate_of_invite(session):
        """
        Sends a high-end styled HTML email (via background task if Celery is available, 
        with sync fallback) and creates an in-app notification.
        """
        candidate = session.candidate

        # 1. In-App Notification (fast database insert)
        try:
            Notification.objects.create(
                recipient=candidate,
                notification_type="INTERVIEW_INVITE",
                dashboard="INTERVIEW",
                message=f"You have been invited to an AI Interview for the {session.job_title} position. Please complete it before {session.expires_at.strftime('%Y-%m-%d')}.",
            )
            logger.info(f"Created in-app notification for {candidate.email}")
        except Exception as e:
            logger.error(f"Failed to create in-app notification: {e}")

        # 2. Dispatch Celery task for background email sending
        try:
            from AIrounds.tasks import task_send_interview_invite
            task_send_interview_invite.delay(str(session.id))
            logger.info(f"Successfully queued background Celery task to send invitation email to {candidate.email}")
            return True
        except Exception as e:
            logger.warning(f"Celery queue not available, falling back to synchronous email delivery: {e}")
            # Fallback to synchronous email delivery in the current thread if Celery is not active/configured
            return InterviewNotifier.send_invite_email_sync(session)

    @staticmethod
    def send_invite_email_sync(session):
        """
        Synchronously renders and dispatches the high-fidelity HTML invitation email.
        Can be run safely in a worker thread (Celery) or synchronously as fallback.
        """
        candidate = session.candidate
        
        # Construct the secure link (Frontend URL + token)
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
        invite_link = f"{frontend_url}/interview/{session.invite_token}"

        # Get active exam credentials from CandidateInterviewLink
        exam_username = "Not generated yet"
        exam_password = "Not generated yet"
        try:
            from AIrounds.models import CandidateInterviewLink
            link = CandidateInterviewLink.objects.get(session=session)
            exam_username = link.exam_username
            exam_password = link.exam_password
        except Exception:
            pass

        # Email Invitation
        try:
            subject = f"Interview Invitation: {session.job_title}"
            
            # Plain text fallback
            email_body = f"""
Hello {candidate.first_name if candidate.first_name else "Candidate"},

Congratulations! You have been shortlisted for the {session.job_title} position.

We invite you to participate in an automated AI Interview as the next step in our hiring process. This platform manages the complete hiring lifecycle from application to handshake.

Access your secure interview room here:
{invite_link}

EXAM LOGIN CREDENTIALS:
Username: {exam_username}
Password: {exam_password}

IMPORTANT INSTRUCTIONS:
1. Ensure you have a working webcam and microphone.
2. The session will perform anti-cheat and identity verification.
3. The link will expire on {session.expires_at.strftime("%Y-%m-%d %H:%M")} UTC.

Best regards,
Hiring Team @ B2LINQ
            """

            # Render premium custom HTML template
            context = {
                "candidate_name": candidate.first_name if candidate.first_name else "Candidate",
                "candidate_email": candidate.email,
                "job_title": session.job_title,
                "invite_link": invite_link,
                "exam_username": exam_username,
                "exam_password": exam_password,
                "expires_at": session.expires_at.strftime("%Y-%m-%d %H:%M"),
            }
            html_body = render_to_string("AIrounds/emails/interview_invite.html", context)

            # Dynamically fetch the notification connection settings
            backend = getattr(settings, "NOTIFICATION_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
            host = getattr(settings, "NOTIFICATION_EMAIL_HOST", "smtp-relay.brevo.com")
            port = int(getattr(settings, "NOTIFICATION_EMAIL_PORT", 587))
            username = getattr(settings, "NOTIFICATION_EMAIL_HOST_USER", "")
            password = getattr(settings, "NOTIFICATION_EMAIL_HOST_PASSWORD", "")
            use_tls = getattr(settings, "NOTIFICATION_EMAIL_USE_TLS", True)
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
                email_body,
                from_email,
                [candidate.email],
                fail_silently=False,
                connection=connection,
                html_message=html_body,
            )
            logger.info(f"Sent interview invite email to {candidate.email} using notification account")
            return True
        except Exception as e:
            logger.error(f"Failed to send invite email: {e}")
            return False
