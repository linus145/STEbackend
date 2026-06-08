"""
AI Credit System Cost & Burn Rates:
- Full Hiring Workflow: 150 credits / run
- Recruitment Agent: 10 credits / run
- Browser Agent Step: 0.1 credits / step
- Resume Screening: 1 credit / resume
- Question Generation: 2 credits / question
- Question Evaluation: 1 credit / question
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from .models import UserCredit, CreditTransaction
from .serializers import UserCreditSerializer, CreditTransactionSerializer, UserCreditAdminSerializer
from .utils import check_and_get_user_credit

class UserCreditViewSet(viewsets.ModelViewSet):
    """
    Administrative ViewSet for CRUD operations on UserCredit models.
    Only accessible by staff/admin users.
    """
    queryset = UserCredit.objects.select_related("user").all()
    serializer_class = UserCreditAdminSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]


class UserCreditBalanceView(APIView):
    """
    API View to retrieve the authenticated user's credit balance and subscription tier limit.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user_credit = check_and_get_user_credit(request.user)
            serializer = UserCreditSerializer(user_credit)
            
            # Map plan types to their monthly limits
            plan_limits = {
                "free": 100,
                "basic": 500,
                "growth": 1000,
                "enterprise": 1500
            }
            plan_limit = plan_limits.get(user_credit.last_allocated_plan_type, 100)
            
            data = serializer.data
            data["plan_limit"] = plan_limit
            
            return Response({
                "status": "success",
                "message": "Credit balance retrieved successfully.",
                "data": data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

class CreditTransactionHistoryView(APIView):
    """
    API View to retrieve the transaction history of the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Trigger self-heal check if user_credit doesn't exist yet
            check_and_get_user_credit(request.user)
            
            transactions = CreditTransaction.objects.filter(user=request.user).order_by("-created_at")
            serializer = CreditTransactionSerializer(transactions, many=True)
            
            return Response({
                "status": "success",
                "message": "Credit transaction history retrieved successfully.",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
