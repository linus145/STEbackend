from django.core.mail import send_mail
from django.conf import settings
from notifications.models import Notification
import logging

logger = logging.getLogger("ai_rounds.notifier")

class InterviewNotifier:
    """Handles communications related to the AI interview process."""

    @staticmethod
    def notify_candidate_of_invite(session):
        """
        Sends an email and an in-app notification to the candidate with their secure link.
        """
        candidate = session.candidate
        # Construct the secure link (Frontend URL + token)
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
        invite_link = f"{frontend_url}/interview/{session.invite_token}"

        # 1. In-App Notification
        try:
            Notification.objects.create(
                recipient=candidate,
                notification_type='INTERVIEW_INVITE',
                message=f"You have been invited to an AI Interview for the {session.job_title} position. Please complete it before {session.expires_at.strftime('%Y-%m-%d')}.",
            )
            logger.info(f"Created in-app notification for {candidate.email}")
        except Exception as e:
            logger.error(f"Failed to create in-app notification: {e}")

        # 2. Email Invitation
        try:
            subject = f"Interview Invitation: {session.job_title}"
            email_body = f"""
Hello {candidate.first_name if candidate.first_name else 'Candidate'},

Congratulations! You have been shortlisted for the {session.job_title} position.

We invite you to participate in an automated AI Interview as the next step in our hiring process. This platform manages the complete hiring lifecycle from application to handshake.

Access your secure interview room here:
{invite_link}

IMPORTANT INSTRUCTIONS:
1. Ensure you have a working webcam and microphone.
2. The session will perform anti-cheat and identity verification.
3. The link will expire on {session.expires_at.strftime('%Y-%m-%d %H:%M')} UTC.

Best regards,
Hiring Team @ B2LINQ
            """
            
            send_mail(
                subject,
                email_body,
                settings.DEFAULT_FROM_EMAIL,
                [candidate.email],
                fail_silently=False,
            )
            logger.info(f"Sent interview invite email to {candidate.email}")
        except Exception as e:
            logger.error(f"Failed to send invite email: {e}")
            return False
            
        return True
