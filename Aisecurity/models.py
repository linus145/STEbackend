from django.db import models
import uuid
from AIrounds.models import InterviewSession


class ProctoringSession(models.Model):
    """
    Main proctoring record for an interview session.
    Tracks overall integrity and session status.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        InterviewSession, on_delete=models.CASCADE, related_name="proctoring"
    )
    is_active = models.BooleanField(default=True)
    integrity_score = models.IntegerField(
        default=100, help_text="Starting score is 100, drops with violations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Proctoring for {self.session.candidate.email} - Score: {self.integrity_score}"


class ViolationLog(models.Model):
    """
    Individual cheating or security violation events.
    """

    VIOLATION_TYPES = [
        ("TAB_SWITCH", "Tab Switch Detected"),
        ("FULLSCREEN_EXIT", "Exited Fullscreen"),
        ("FACE_MISSING", "Candidate Face Not Detected"),
        ("MULTIPLE_FACES", "Multiple Faces Detected"),
        ("PHONE_DETECTED", "Mobile Phone Detected"),
        ("HEAD_AWAY", "Looking Away From Screen"),
        ("UNAUTHORIZED_DEVICE", "External Device Plugged In"),
        ("CLIPBOARD_ACCESS", "Copy/Paste Attempted"),
        ("SPLIT_SCREEN_DETECTED", "Split Screen Mode Active"),
        ("EXTERNAL_TOOL_USAGE", "Interaction with External Tool"),
        ("SCREENSHOT_ATTEMPT", "Screenshot or DevTools Attempt"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proctoring_session = models.ForeignKey(
        ProctoringSession, on_delete=models.CASCADE, related_name="violations"
    )
    violation_type = models.CharField(max_length=50, choices=VIOLATION_TYPES)
    severity = models.CharField(max_length=20, default="MEDIUM")  # LOW, MEDIUM, HIGH
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(
        default=dict, blank=True
    )  # To store e.g. confidence score, browser info
    screenshot_url = models.URLField(max_length=500, null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return (
            f"{self.violation_type} - {self.proctoring_session.session.candidate.email}"
        )


# Signals to update integrity score (Implemented later)
# from django.db.models.signals import post_save
# from django.dispatch import receiver

# @receiver(post_save, sender=ViolationLog)
# def update_integrity_score(sender, instance, created, **kwargs):
#     if created:
#         session = instance.proctoring_session
#         penalty = 5
#         if instance.severity == 'HIGH':
#             penalty = 20
#         elif instance.severity == 'MEDIUM':
#             penalty = 10

#         session.integrity_score = max(0, session.integrity_score - penalty)
#         session.save()
