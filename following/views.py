from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from django.contrib.auth import get_user_model

from .models import Follow, CompanyFollow
from .serializers import FollowUserSerializer, CompanyFollowSerializer
from maincore.pagination import StandardResultsSetPagination
from startups.models import CompanyProfile

User = get_user_model()


# ═══════════════════════════════════════════════════════
# USER FOLLOW
# ═══════════════════════════════════════════════════════

class ToggleFollowView(APIView):
    """POST { "user_id": "<uuid>" } to follow/unfollow a user (toggle)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user_id = request.data.get("user_id")
        if not user_id:
            return Response({"error": "user_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        if str(user_id) == str(request.user.id):
            return Response({"error": "You cannot follow yourself."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check for soft-deleted follow
        existing = Follow.all_objects.filter(follower=request.user, following=target_user).first()

        if existing:
            if existing.is_deleted:
                existing.restore()
                return Response({"status": "following", "user_id": str(user_id)}, status=status.HTTP_201_CREATED)
            else:
                existing.delete()
                return Response({"status": "unfollowed", "user_id": str(user_id)}, status=status.HTTP_200_OK)
        else:
            Follow.objects.create(follower=request.user, following=target_user)
            return Response({"status": "following", "user_id": str(user_id)}, status=status.HTTP_201_CREATED)


class FollowersListView(ListAPIView):
    """List users who follow a given user. Defaults to the authenticated user."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FollowUserSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user_id = self.kwargs.get("user_id", self.request.user.id)
        follower_ids = Follow.objects.filter(following_id=user_id).values_list("follower_id", flat=True)
        return User.objects.filter(id__in=follower_ids).select_related(
            "founder_profile", "investor_profile", "mentor_profile"
        )


class FollowingListView(ListAPIView):
    """List users that a given user follows. Defaults to the authenticated user."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FollowUserSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user_id = self.kwargs.get("user_id", self.request.user.id)
        following_ids = Follow.objects.filter(follower_id=user_id).values_list("following_id", flat=True)
        return User.objects.filter(id__in=following_ids).select_related(
            "founder_profile", "investor_profile", "mentor_profile"
        )


class FollowCountsView(APIView):
    """GET follower/following counts and follow status for a user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, user_id=None):
        target_id = user_id or request.user.id
        try:
            target_user = User.objects.get(id=target_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        followers_count = Follow.objects.filter(following=target_user).count()
        following_count = Follow.objects.filter(follower=target_user).count()

        is_following = False
        if str(target_id) != str(request.user.id):
            is_following = Follow.objects.filter(follower=request.user, following=target_user).exists()

        return Response({
            "followers_count": followers_count,
            "following_count": following_count,
            "is_following": is_following,
        })


# ═══════════════════════════════════════════════════════
# COMPANY FOLLOW
# ═══════════════════════════════════════════════════════

class ToggleCompanyFollowView(APIView):
    """POST { "company_id": "<uuid>" } to follow/unfollow a company (toggle)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        company_id = request.data.get("company_id")
        if not company_id:
            return Response({"error": "company_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            company = CompanyProfile.objects.get(id=company_id)
        except CompanyProfile.DoesNotExist:
            return Response({"error": "Company not found."}, status=status.HTTP_404_NOT_FOUND)

        existing = CompanyFollow.all_objects.filter(follower=request.user, company=company).first()

        if existing:
            if existing.is_deleted:
                existing.restore()
                return Response({"status": "following", "company_id": str(company_id)}, status=status.HTTP_201_CREATED)
            else:
                existing.delete()
                return Response({"status": "unfollowed", "company_id": str(company_id)}, status=status.HTTP_200_OK)
        else:
            CompanyFollow.objects.create(follower=request.user, company=company)
            return Response({"status": "following", "company_id": str(company_id)}, status=status.HTTP_201_CREATED)


class CompanyFollowersListView(ListAPIView):
    """List users who follow a given company."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FollowUserSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        company_id = self.kwargs.get("company_id")
        follower_ids = CompanyFollow.objects.filter(company_id=company_id).values_list("follower_id", flat=True)
        return User.objects.filter(id__in=follower_ids).select_related(
            "founder_profile", "investor_profile", "mentor_profile"
        )


class CompanyFollowCountsView(APIView):
    """GET followers count and follow status for a company."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, company_id):
        try:
            company = CompanyProfile.objects.get(id=company_id)
        except CompanyProfile.DoesNotExist:
            return Response({"error": "Company not found."}, status=status.HTTP_404_NOT_FOUND)

        followers_count = CompanyFollow.objects.filter(company=company).count()
        is_following = CompanyFollow.objects.filter(follower=request.user, company=company).exists()

        return Response({
            "followers_count": followers_count,
            "is_following": is_following,
        })


class MyFollowedCompaniesView(ListAPIView):
    """List companies the authenticated user follows."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CompanyFollowSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return CompanyFollow.objects.filter(
            follower=self.request.user
        ).select_related("company")
