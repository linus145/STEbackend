from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from .serializers import FounderSerializer, FounderUpdateSerializer
from .services import FounderService

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class FounderListView(generics.ListAPIView):
    """
    Returns a paginated list of all founders. Supports filtering via query params.
    """
    permission_classes = (AllowAny,)
    serializer_class = FounderSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        filters = {
            'primary_industry': self.request.query_params.get('industry'),
            'min_experience': self.request.query_params.get('min_experience'),
        }
        return FounderService.get_all_founders(filters=filters)

class FounderDetailView(APIView):
    """
    Retrieves a single founder profile by UUID.
    """
    permission_classes = (AllowAny,)

    def get(self, request, founder_id, *args, **kwargs):
        founder = FounderService.get_founder_by_id(founder_id)
        if not founder:
            return Response({'detail': 'Founder not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = FounderSerializer(founder)
        return Response(serializer.data, status=status.HTTP_200_OK)

class MyFounderProfileView(APIView):
    """
    Allows a user to retrieve or update their own founder profile.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        founder = FounderService.get_founder_by_user(request.user)
        if not founder:
            return Response({'detail': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = FounderSerializer(founder)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, *args, **kwargs):
        if request.user.role != 'founder':
            return Response({'detail': 'Only founders can have a founder profile.'}, status=status.HTTP_403_FORBIDDEN)
            
        serializer = FounderUpdateSerializer(data=request.data)
        if serializer.is_valid():
            founder = FounderService.create_or_update_profile(request.user, serializer.validated_data)
            response_serializer = FounderSerializer(founder)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
