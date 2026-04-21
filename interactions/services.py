from django.db import transaction
from django.contrib.auth import get_user_model
from .models import Like, Dislike, Comment
from posts.models import Post

User = get_user_model()

class InteractionService:
    @staticmethod
    def toggle_like(user: User, post_id: str) -> dict:
        """
        Toggles a like on a post.
        """
        try:
            post = Post.objects.get(id=post_id)
        except Post.DoesNotExist:
            return {"error": "Post not found."}

        with transaction.atomic():
            # Check for existing interaction (including soft-deleted) to prevent DB integrity clashes
            like = Like.all_objects.filter(user=user, post=post).first()
            if like:
                if like.is_deleted:
                    like.restore()
                    result = {"action": "liked"}
                else:
                    like.delete()
                    result = {"action": "unliked"}
            else:
                Like.objects.create(user=user, post=post)
                result = {"action": "liked"}
                
        return result

    @staticmethod
    def add_comment(user: User, validated_data: dict) -> Comment:
        return Comment.objects.create(user=user, **validated_data)

    @staticmethod
    def get_comments_for_post(post_id: str):
        return Comment.objects.filter(post_id=post_id).select_related('user').order_by('-created_at')

    @staticmethod
    def delete_comment(user: User, comment_id: str) -> bool:
        try:
            comment = Comment.objects.get(id=comment_id, user=user)
            comment.delete()
            return True
        except Comment.DoesNotExist:
            return False
