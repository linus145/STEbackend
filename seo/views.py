import urllib.parse
from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status, serializers
from .models import Page, PageSEO

class PageSEOSerializer(serializers.ModelSerializer):
    class Meta:
        model = PageSEO
        fields = ['meta_title', 'meta_description', 'meta_keywords', 'og_title', 'og_description', 'og_image', 'og_type', 'page_type', 'is_noindex', 'is_nofollow']

class PageSerializer(serializers.ModelSerializer):
    seo = PageSEOSerializer()

    class Meta:
        model = Page
        fields = ['name', 'url_path', 'seo']

def normalize_url_path(raw_path: str) -> str:
    """
    Standardize the URL path:
    1. URL-decode (%2F -> /)
    2. Strip query parameters and fragment hashes
    3. Normalize slashes: strip trailing slashes (except root)
    4. Force lowercase
    """
    if not raw_path:
        return '/'
    
    # URL decode
    decoded = urllib.parse.unquote(raw_path)
    
    # Strip query parameters and hashes
    parsed = urllib.parse.urlparse(decoded)
    path = parsed.path.strip()
    
    # Collapse double slashes and strip leading/trailing spaces
    path = '/' + '/'.join(filter(None, path.split('/')))
    
    # Convert to lowercase
    path = path.lower()
    
    return path

class PageSEOQueryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        path_param = request.query_params.get('path', None)
        if not path_param:
            return Response({"detail": "Query parameter 'path' is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Normalize the path parameter
        normalized_path = normalize_url_path(path_param)
        
        # Try to retrieve from cache
        cache_key = f"seo_page_path:{normalized_path}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        
        try:
            page = Page.objects.get(url_path=normalized_path)
            serializer = PageSerializer(page)
            data = serializer.data
            # Cache the response data for 24 hours (86400 seconds)
            cache.set(cache_key, data, 86400)
            return Response(data)
        except Page.DoesNotExist:
            # Fallback path mapping: e.g. for dynamic blog details /blogs/some-slug, fall back to /blogs
            if normalized_path.startswith('/blogs/') and normalized_path != '/blogs/':
                fallback_path = '/blogs'
                cache_key_fallback = f"seo_page_path:{fallback_path}"
                cached_fallback = cache.get(cache_key_fallback)
                if cached_fallback:
                    return Response(cached_fallback)
                
                try:
                    page = Page.objects.get(url_path=fallback_path)
                    serializer = PageSerializer(page)
                    data = serializer.data
                    cache.set(cache_key_fallback, data, 86400)
                    return Response(data)
                except Page.DoesNotExist:
                    pass
            
            return Response({
                "name": normalized_path,
                "url_path": normalized_path,
                "seo": None
            }, status=status.HTTP_200_OK)

