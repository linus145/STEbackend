from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import AboutUs, Blog, JobOpening, ContactInquiry
from .serializers import (
    AboutUsSerializer,
    BlogSerializer,
    JobOpeningSerializer,
    ContactInquirySerializer,
)


class AboutUsView(APIView):
    def get(self, request):
        about = AboutUs.objects.first()
        if not about:
            return Response(
                {"detail": "About Us content not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = AboutUsSerializer(about)
        return Response(serializer.data)


class BlogListView(generics.ListAPIView):
    queryset = Blog.objects.all().order_by("-date")
    serializer_class = BlogSerializer


class BlogDetailView(generics.RetrieveAPIView):
    queryset = Blog.objects.all()
    serializer_class = BlogSerializer
    lookup_field = "slug"


class JobOpeningListView(generics.ListAPIView):
    queryset = JobOpening.objects.filter(is_active=True).order_by("-created_at")
    serializer_class = JobOpeningSerializer


class ContactInquiryCreateView(generics.CreateAPIView):
    queryset = ContactInquiry.objects.all()
    serializer_class = ContactInquirySerializer
