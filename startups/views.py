from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from .serializers import StartupSerializer, StartupCreateUpdateSerializer
from .services import StartupService

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class StartupListView(generics.ListAPIView):
    permission_classes = (AllowAny,)
    serializer_class = StartupSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        filters = {
            'industry': self.request.query_params.get('industry'),
            'stage': self.request.query_params.get('stage'),
        }
        return StartupService.get_all_startups(filters=filters)

class MyStartupsView(APIView):
    """
    Manage the founder's own startups.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        if request.user.role != 'FOUNDER':
             return Response({'detail': 'Only founders have startups.'}, status=status.HTTP_403_FORBIDDEN)
        
        startups = StartupService.get_startups_by_user(request.user)
        serializer = StartupSerializer(startups, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        if request.user.role != 'FOUNDER':
             return Response({'detail': 'Only founders can create startups.'}, status=status.HTTP_403_FORBIDDEN)
             
        serializer = StartupCreateUpdateSerializer(data=request.data)
        if serializer.is_valid():
            startup = StartupService.create_startup(request.user, serializer.validated_data)
            return Response(StartupSerializer(startup).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class StartupDetailView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, startup_id, *args, **kwargs):
        startup = StartupService.get_startup_by_id(startup_id)
        if not startup:
            return Response({'detail': 'Startup not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = StartupSerializer(startup)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, startup_id, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
            
        startup = StartupService.get_startup_by_id(startup_id)
        if not startup:
            return Response({'detail': 'Startup not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        if startup.founder != request.user:
            return Response({'detail': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
            
        serializer = StartupCreateUpdateSerializer(data=request.data)
        if serializer.is_valid():
            updated_startup = StartupService.update_startup(startup, serializer.validated_data)
            return Response(StartupSerializer(updated_startup).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, startup_id, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
            
        startup = StartupService.get_startup_by_id(startup_id)
        if not startup:
            return Response({'detail': 'Startup not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        if startup.founder != request.user:
            return Response({'detail': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
            
        StartupService.delete_startup(startup)
        return Response(status=status.HTTP_204_NO_CONTENT)
