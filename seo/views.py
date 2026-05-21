from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status, serializers
from .models import Page, PageSEO

class PageSEOSerializer(serializers.ModelSerializer):
    class Meta:
        model = PageSEO
        fields = ['meta_title', 'meta_description', 'meta_keywords', 'og_title', 'og_description', 'og_image', 'og_type']

class PageSerializer(serializers.ModelSerializer):
    seo = PageSEOSerializer()

    class Meta:
        model = Page
        fields = ['name', 'url_path', 'seo']

class PageSEOQueryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        path = request.query_params.get('path', None)
        if not path:
            return Response({"detail": "Query parameter 'path' is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            page = Page.objects.get(url_path=path)
            serializer = PageSerializer(page)
            return Response(serializer.data)
        except Page.DoesNotExist:
            # Fallback path mapping: e.g. for dynamic blog details /blogs/some-slug, fall back to /blogs
            if path.startswith('/blogs/') and path != '/blogs/':
                try:
                    page = Page.objects.get(url_path='/blogs')
                    serializer = PageSerializer(page)
                    return Response(serializer.data)
                except Page.DoesNotExist:
                    pass
            
            return Response({"detail": "SEO settings not found for this path."}, status=status.HTTP_404_NOT_FOUND)
