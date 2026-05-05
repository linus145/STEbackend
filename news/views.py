from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import News
from .serializers import NewsSerializer, NewsCreateSerializer
from maincore.pagination import StandardResultsSetPagination

class NewsListView(generics.ListAPIView):
    """
    List news articles with filtering for trending, popular, and top news.
    """
    serializer_class = NewsSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = News.objects.all()
        category = self.request.query_params.get('category', None)
        
        if category == 'trending':
            queryset = queryset.filter(is_trending=True)
        elif category == 'popular':
            queryset = queryset.filter(is_popular=True)
        elif category == 'top':
            queryset = queryset.filter(is_top_news=True)
            
        return queryset

class NewsCreateView(generics.CreateAPIView):
    """
    Create a new news article.
    """
    serializer_class = NewsCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

class NewsDetailView(generics.RetrieveAPIView):
    """
    Get details of a single news article.
    """
    queryset = News.objects.all()
    serializer_class = NewsSerializer
    permission_classes = [permissions.IsAuthenticated]
