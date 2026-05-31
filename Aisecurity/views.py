from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import UserRateThrottle
from .models import ProctoringSession, ViolationLog
from AIrounds.models import InterviewSession
from .serializers import ProctoringSessionSerializer, ViolationLogSerializer


class LogViolationThrottle(UserRateThrottle):
    rate = '60/minute'


class CodeExecutionThrottle(UserRateThrottle):
    rate = '15/minute'


class LogViolationView(APIView):
    """
    API for the Exam Portal to log a proctoring violation.
    Candidates use this to report tab switches, face missing, etc.
    """
    permission_classes = (AllowAny,)
    throttle_classes = [LogViolationThrottle]

    def post(self, request):
        session_id = request.data.get('session_id')
        violation_type = request.data.get('violation_type')
        metadata = request.data.get('metadata', {})
        severity = request.data.get('severity', 'MEDIUM')
        
        if not session_id or not violation_type:
            return Response({"status": "error", "message": "session_id and violation_type are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 1. Get interview session and verify ownership/authorization
            interview_session = InterviewSession.objects.get(id=session_id)
            
            is_authorized = False
            if request.user and not request.user.is_anonymous:
                if request.user.is_staff or request.user.is_superuser:
                    is_authorized = True
                elif interview_session.candidate == request.user:
                    is_authorized = True
                elif hasattr(request.user, 'company_profile') and interview_session.application and interview_session.application.job.company == request.user.company_profile:
                    is_authorized = True
            else:
                # Allow anonymous candidate requests if the session is active (meaning exam is in progress)
                if interview_session.status == 'ACTIVE':
                    is_authorized = True
                    
            if not is_authorized:
                return Response({"status": "error", "message": "Unauthorized access to this session."}, status=status.HTTP_403_FORBIDDEN)
                
            proctor_session, _ = ProctoringSession.objects.get_or_create(session=interview_session)
            
            duration_seconds = request.data.get('duration_seconds', metadata.get('duration_seconds', 0.0))

            # 2. Log the violation
            violation = ViolationLog.objects.create(
                proctoring_session=proctor_session,
                violation_type=violation_type,
                severity=severity,
                duration_seconds=float(duration_seconds),
                metadata=metadata
            )
            
            # 3. Dynamic Score Update
            # Severity mapping
            penalty = 5
            if severity == 'HIGH': penalty = 15
            elif severity == 'LOW': penalty = 2
            
            proctor_session.integrity_score = max(0, proctor_session.integrity_score - penalty)
            proctor_session.save()
            
            return Response({
                "status": "success", 
                "violation_id": str(violation.id),
                "current_integrity_score": proctor_session.integrity_score
            }, status=status.HTTP_201_CREATED)
            
        except InterviewSession.DoesNotExist:
            return Response({"status": "error", "message": "Interview session not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProctoringReportView(APIView):
    """
    API for recruiters to view the integrity report of a specific candidate.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, session_id):
        try:
            # Authorization check: only let recruiters (staff/employer/owner) or candidate themselves view reports
            proctor_session = ProctoringSession.objects.select_related(
                'session__candidate', 
                'session__application__job__company'
            ).prefetch_related('violations').get(session_id=session_id)
            
            is_authorized = False
            if request.user.is_staff:
                is_authorized = True
            elif proctor_session.session.candidate == request.user:
                is_authorized = True
            elif hasattr(request.user, 'company_profile') and proctor_session.session.application and proctor_session.session.application.job.company == request.user.company_profile:
                is_authorized = True
                
            if not is_authorized:
                return Response({"status": "error", "message": "Unauthorized access to this report."}, status=status.HTTP_403_FORBIDDEN)
                
            serializer = ProctoringSessionSerializer(proctor_session)
            return Response(serializer.data)
        except ProctoringSession.DoesNotExist:
            return Response({"status": "error", "message": "No proctoring data found for this session."}, status=status.HTTP_404_NOT_FOUND)


class CodeExecutionView(APIView):
    """
    Secure code execution endpoint for the Exam Coding Environment.
    Runs candidate code on the server via sandboxed subprocess.
    Uses the server's own Python (with Pandas, NumPy, etc.).
    """
    permission_classes = (IsAuthenticated,)
    throttle_classes = [CodeExecutionThrottle]

    def post(self, request):
        source_code = request.data.get('source_code', '')
        language = request.data.get('language', 'python')
        stdin = request.data.get('stdin', '')

        if not source_code.strip():
            return Response({
                'stdout': '',
                'stderr': 'No code provided.',
                'success': False,
            }, status=status.HTTP_400_BAD_REQUEST)

        from .code_executor import execute_code
        result = execute_code(source_code, language, stdin)

        return Response(result, status=status.HTTP_200_OK)
