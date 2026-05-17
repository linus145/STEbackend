from django.db.models.signals import post_save
from django.dispatch import receiver
from interactions.models import Like, Connection
from comments.models import Comment
from .models import Notification

@receiver(post_save, sender=Like)
def create_like_notification(sender, instance, created, **kwargs):
    if created:
        # Don't notify if user likes their own post
        if instance.user != instance.post.author:
            Notification.objects.create(
                recipient=instance.post.author,
                sender=instance.user,
                notification_type='LIKE',
                post_id=instance.post.id,
                message=f"{instance.user.first_name} liked your post."
            )

@receiver(post_save, sender=Comment)
def create_comment_notification(sender, instance, created, **kwargs):
    if created:
        if instance.user != instance.post.author:
            Notification.objects.create(
                recipient=instance.post.author,
                sender=instance.user,
                notification_type='COMMENT',
                post_id=instance.post.id,
                message=f"{instance.user.first_name} commented on your post."
            )

@receiver(post_save, sender=Connection)
def create_connection_notification(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            recipient=instance.receiver,
            sender=instance.sender,
            notification_type='CONNECTION_REQUEST',
            message=f"{instance.sender.first_name} sent you a connection request."
        )
    else:
        # Check if status was changed to ACCEPTED
        if instance.status == 'ACCEPTED':
            # Check if notification already exists to avoid duplicates on multiple saves
            if not Notification.objects.filter(
                recipient=instance.sender,
                sender=instance.receiver,
                notification_type='CONNECTION_ACCEPTED'
            ).exists():
                Notification.objects.create(
                    recipient=instance.sender,
                    sender=instance.receiver,
                    notification_type='CONNECTION_ACCEPTED',
                    message=f"{instance.receiver.first_name} accepted your connection request."
                )
        elif instance.status == 'REJECTED':
             # Notify the sender that their request was rejected (optional but requested)
             if not Notification.objects.filter(
                recipient=instance.sender,
                sender=instance.receiver,
                notification_type='CONNECTION_REJECTED'
            ).exists():
                Notification.objects.create(
                    recipient=instance.sender,
                    sender=instance.receiver,
                    notification_type='CONNECTION_REJECTED',
                    message=f"{instance.receiver.first_name} declined your connection request."
                )

@receiver(post_save, sender='jobs.JobApplication')
def create_job_application_notification(sender, instance, created, **kwargs):
    if created:
        recipient = None
        try:
            if instance.job and instance.job.company:
                recipient = instance.job.company.owner
        except Exception:
            pass
        if recipient:
            total_applicants = 1
            try:
                total_applicants = instance._meta.model.objects.filter(job=instance.job).count()
            except Exception:
                try:
                    total_applicants = instance.job.applications.count()
                except Exception:
                    pass
            Notification.objects.create(
                recipient=recipient,
                sender=instance.applicant,
                notification_type='NEW_APPLICATION',
                dashboard='RECRUITER',
                message=f"Total {total_applicants} applicants for your '{instance.job.title}'."
            )

@receiver(post_save, sender='AIrounds.InterviewSession')
def create_interview_session_notification(sender, instance, created, **kwargs):
    if not created:
        if instance.status == 'COMPLETED':
            recipient = None
            try:
                if instance.application and instance.application.job and instance.application.job.company:
                    recipient = instance.application.job.company.owner
            except Exception:
                pass
            if recipient:
                Notification.objects.create(
                    recipient=recipient,
                    sender=instance.candidate,
                    notification_type='INTERVIEW_COMPLETED',
                    dashboard='INTERVIEW',
                    message=f"AI Interview completed by {instance.candidate.first_name or instance.candidate.email} for '{instance.job_title}'. Score: {instance.overall_score}%."
                )

@receiver(post_save, sender='leave_management.LeaveRequest')
def create_leave_request_notification(sender, instance, created, **kwargs):
    if created:
        recipient = None
        try:
            if instance.startup:
                recipient = instance.startup.founder
        except Exception:
            pass
        if recipient:
            Notification.objects.create(
                recipient=recipient,
                sender=instance.employee.user,
                notification_type='LEAVE_REQUEST',
                dashboard='HR',
                message=f"Leave request submitted by {instance.employee.first_name} {instance.employee.last_name} ({instance.start_date} to {instance.end_date})."
            )
    else:
        if instance.status in ['APPROVED', 'REJECTED']:
            recipient = None
            try:
                if instance.employee:
                    recipient = instance.employee.user
            except Exception:
                pass
            if recipient:
                n_type = 'LEAVE_APPROVED' if instance.status == 'APPROVED' else 'LEAVE_REJECTED'
                status_str = "approved" if instance.status == 'APPROVED' else "rejected"
                Notification.objects.create(
                    recipient=recipient,
                    notification_type=n_type,
                    dashboard='HR',
                    message=f"Your leave request for {instance.start_date} to {instance.end_date} has been {status_str}."
                )

@receiver(post_save, sender='chat.Message')
def create_message_notification(sender, instance, created, **kwargs):
    if created:
        try:
            if instance.room and instance.room.room_type == 'direct':
                # Get the other participants in this chat room
                other_participants = instance.room.participants.exclude(id=instance.sender.id)
                for recipient in other_participants:
                    text_snippet = instance.text[:50] + '...' if len(instance.text) > 50 else instance.text
                    sender_name = instance.sender.first_name or instance.sender.email
                    Notification.objects.create(
                        recipient=recipient,
                        sender=instance.sender,
                        notification_type='NEW_MESSAGE',
                        dashboard='RECRUITER',
                        message=f"New message from {sender_name}: '{text_snippet}'"
                    )
        except Exception:
            pass
