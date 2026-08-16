import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from maincore.basemodel import SoftDeleteModel


class Follow(SoftDeleteModel):
    """
    One-way follow relationship between users (LinkedIn-style).
    - follower: the user who follows
    - following: the user being followed
    Unlike Connections, follows are instant (no approval needed).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="following_set",
        help_text="The user who follows",
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="followers_set",
        help_text="The user being followed",
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Follow"
        verbose_name_plural = "Follows"
        unique_together = ("follower", "following")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.follower.email} follows {self.following.email}"


class CompanyFollow(SoftDeleteModel):
    """
    One-way follow relationship between a user and a company (LinkedIn-style).
    - follower: the user who follows
    - company: the CompanyProfile being followed
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company_follows",
        help_text="The user who follows the company",
    )
    company = models.ForeignKey(
        "startups.CompanyProfile",
        on_delete=models.CASCADE,
        related_name="followers",
        help_text="The company being followed",
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Company Follow"
        verbose_name_plural = "Company Follows"
        unique_together = ("follower", "company")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.follower.email} follows {self.company.company_name}"
