from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import AIScreeningReport
from .serializers import AIScreeningReportSerializer

class AIScreeningHistoryView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        reports = AIScreeningReport.objects.filter(recruiter=request.user)
        serializer = AIScreeningReportSerializer(reports, many=True)
        return Response({
            "status": "success",
            "message": "Screening history fetched.",
            "data": serializer.data
        })
