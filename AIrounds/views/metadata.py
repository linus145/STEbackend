from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from AIrounds.models import InterviewRound, InterviewSession
from AIrounds.views.base import ResponseMixin

SUGGESTED_TOPICS = {
    "ENTRY": ['Variables & Types', 'Conditional Logic', 'Loops & Iterations', 'String Manipulation', 'Basic Arrays', 'Simple Functions'],
    "MID": ['Recursion', 'Object-Oriented Design', 'Exceptions & File I/O', 'Data Structures (Stacks/Queues/HashMaps)', 'Searching & Sorting', 'API Handling'],
    "SENIOR": ['Dynamic Programming', 'Graph Algorithms', 'Trees & BST', 'Concurrency & Threading', 'SQL & Database Queries', 'Code Optimization'],
    "LEAD": ['System Design Coding', 'Design Patterns', 'Scalability & Load Snips', 'Secure Cryptography', 'Distributed Algorithms']
}

SUGGESTED_FRAMEWORKS = {
    "PYTHON": ['Django', 'Flask', 'FastAPI', 'Pandas & NumPy', 'PyTorch'],
    "JAVASCRIPT": ['React', 'Node.js', 'Express', 'Next.js', 'Vue.js'],
    "TYPESCRIPT": ['NestJS', 'React with TS', 'Next.js with TS', 'Express with TS'],
    "JAVA": ['Spring Boot', 'Hibernate', 'Spring Security'],
    "CPP": ['Qt', 'Boost', 'STL Library'],
    "CSHARP": ['.NET Core', 'ASP.NET MVC', 'Entity Framework'],
    "GO": ['Gin', 'Echo', 'Fiber', 'GORM']
}

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
            "round_categories": [{"value": k, "label": v} for k, v in InterviewRound.ROUND_CATEGORY_CHOICES],
            "question_formats": [{"value": k, "label": v} for k, v in InterviewRound.QUESTION_FORMAT_CHOICES],
            "programming_languages": [{"value": k, "label": v} for k, v in InterviewRound.PROGRAMMING_LANGUAGE_CHOICES if k],
            "suggested_topics": SUGGESTED_TOPICS,
            "suggested_frameworks": SUGGESTED_FRAMEWORKS,
        }
        return self.build_response("success", "Metadata retrieved.", data)

