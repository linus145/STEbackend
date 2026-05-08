from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from AIrounds.models import InterviewRound, InterviewSession
from AIrounds.views.base import ResponseMixin

class InterviewMetadataView(APIView, ResponseMixin):
    """
    Returns predefined choices for designations, strategy tiers, and difficulty levels.
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        data = {
            "designations": [{"value": k, "label": v} for k, v in InterviewRound.DESIGNATION_CHOICES],
            "strategy_tiers": [{"value": k, "label": v} for k, v in InterviewSession.STRATEGY_TIER_CHOICES],
            "difficulty_levels": [{"value": k, "label": v} for k, v in InterviewSession.EVALUATION_DEPTH_CHOICES],
            "question_formats": [{"value": k, "label": v} for k, v in InterviewRound.QUESTION_FORMAT_CHOICES],
            "programming_languages": [{"value": k, "label": v} for k, v in InterviewRound.PROGRAMMING_LANGUAGE_CHOICES if k],
        }
        return self.build_response("success", "Metadata retrieved.", data)

