from django.db.models import Count, Q, Exists, OuterRef, Subquery, IntegerField
from django.db.models.functions import Coalesce
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from .models import Post
from interactions.models import (
    Like,
    Dislike,
    Comment,
)  # Cross-app import for optimization

User = get_user_model()


class PostService:
    @staticmethod
    def get_annotated_posts(current_user=None):
        """
        Retrieves all posts natively annotated with like and comment counts natively in the DB.
        Leverages prefetch_related and select_related to eliminate N+1 queries.
        """
        # Use isolated Subqueries with explicit row limiting ([:1]) to ensure precision
        # and prevent SQL errors or zero-count bug on some DB engine variations.
        likes_subquery = (
            Like.objects.filter(post=OuterRef("pk"))
            .values("post")
            .annotate(c=Count("pk"))
            .values("c")[:1]
        )
        comments_subquery = (
            Comment.objects.filter(post=OuterRef("pk"))
            .values("post")
            .annotate(c=Count("pk"))
            .values("c")[:1]
        )

        qs = Post.objects.select_related(
            "author", 
            "author__founder_profile", 
            "author__investor_profile"
        ).annotate(
            likes_count=Coalesce(
                Subquery(likes_subquery, output_field=IntegerField()), 0
            ),
            comments_count=Coalesce(
                Subquery(comments_subquery, output_field=IntegerField()), 0
            ),
        )

        if current_user and current_user.is_authenticated:
            # Check if current user has liked the post seamlessly in the same query
            has_liked_subquery = Like.objects.filter(
                post=OuterRef("pk"), user=current_user
            )
            qs = qs.annotate(user_has_liked=Exists(has_liked_subquery))

        return qs.order_by("-created_at")

    @staticmethod
    def get_post_by_id(post_id: str, current_user=None):
        try:
            return PostService.get_annotated_posts(current_user).get(id=post_id)
        except Post.DoesNotExist:
            return None

    @staticmethod
    def create_post(user: User, validated_data: dict) -> Post:
        return Post.objects.create(author=user, **validated_data)

    @staticmethod
    def update_post(post: Post, validated_data: dict) -> Post:
        for attr, value in validated_data.items():
            setattr(post, attr, value)
        post.save()
        return post

    @staticmethod
    def delete_post(post: Post):
        if post.media_url:
            from maincore.imagekit_utils import ImageKitService
            ImageKitService.delete_file(post.media_url)
        post.delete()
