from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import Comment
from .serializers import CommentSerializer, CommentCreateSerializer

class PostCommentsListView(generics.ListAPIView):
    serializer_class = CommentSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        post_id = self.kwargs.get('post_id')
        return Comment.objects.filter(post_id=post_id).select_related(
            'user', 
            'user__founder_profile', 
            'user__investor_profile'
        )

class CommentCreateView(generics.CreateAPIView):
    serializer_class = CommentCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
