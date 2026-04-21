from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from .serializers import InvestorSerializer, InvestorUpdateSerializer
from .services import InvestorService

# Ideally import RequestResponseMixin from useraccounts, 
# for independence we'll quickly redefine or use standard DRF responses.
class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class InvestorListView(generics.ListAPIView):
    permission_classes = (AllowAny,)
    serializer_class = InvestorSerializer
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        filters = {
            'firm_name': self.request.query_params.get('firm_name'),
        }
        return InvestorService.get_all_investors(filters=filters)

class InvestorDetailView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, investor_id, *args, **kwargs):
        investor = InvestorService.get_investor_by_id(investor_id)
        if not investor:
            return Response({'detail': 'Investor not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = InvestorSerializer(investor)
        return Response(serializer.data, status=status.HTTP_200_OK)

class MyInvestorProfileView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        investor = InvestorService.get_investor_by_user(request.user)
        if not investor:
            return Response({'detail': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = InvestorSerializer(investor)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, *args, **kwargs):
        if request.user.role != 'INVESTOR':
            return Response({'detail': 'Only investors can update an investor profile.'}, status=status.HTTP_403_FORBIDDEN)
            
        serializer = InvestorUpdateSerializer(data=request.data)
        if serializer.is_valid():
            investor = InvestorService.create_or_update_profile(request.user, serializer.validated_data)
            return Response(InvestorSerializer(investor).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
