import time
from django.conf import settings
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from .serializers import PostSerializer, PostCreateUpdateSerializer
from .services import PostService


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


from maincore.imagekit_utils import ImageKitService

class ImageKitAuthView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        auth_params = ImageKitService.get_auth_params()
        if not auth_params:
            return Response(
                {"error": "ImageKit credentials not configured."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(auth_params, status=status.HTTP_200_OK)


class PostListView(generics.ListAPIView):
    """
    Returns a paginated list of posts with interaction aggregations.
    """

    permission_classes = (AllowAny,)
    serializer_class = PostSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user if self.request.user.is_authenticated else None
        return PostService.get_annotated_posts(current_user=user)


class PostCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        serializer = PostCreateUpdateSerializer(data=request.data)
        if serializer.is_valid():
            post = PostService.create_post(request.user, serializer.validated_data)
            response_serializer = PostSerializer(post)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PostDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, post_id, *args, **kwargs):
        post = PostService.get_post_by_id(post_id, current_user=request.user)
        if not post:
            return Response(
                {"detail": "Post not found."}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = PostSerializer(post)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, post_id, *args, **kwargs):
        post = PostService.get_post_by_id(post_id)
        if not post:
            return Response(
                {"detail": "Post not found."}, status=status.HTTP_404_NOT_FOUND
            )
        if post.author != request.user:
            return Response(
                {"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN
            )

        serializer = PostCreateUpdateSerializer(data=request.data)
        if serializer.is_valid():
            updated_post = PostService.update_post(post, serializer.validated_data)
            return Response(
                PostSerializer(updated_post).data, status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, post_id, *args, **kwargs):
        post = PostService.get_post_by_id(post_id)
        if not post:
            return Response(
                {"detail": "Post not found."}, status=status.HTTP_404_NOT_FOUND
            )
        if post.author != request.user:
            return Response(
                {"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN
            )

        PostService.delete_post(post)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserPostListView(generics.ListAPIView):
    """
    Returns a paginated list of posts specifically created by a user.
    """

    permission_classes = (AllowAny,)
    serializer_class = PostSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user_id = self.kwargs.get("user_id")
        current_user = self.request.user if self.request.user.is_authenticated else None
        return PostService.get_annotated_posts(current_user=current_user).filter(
            author_id=user_id
        )
