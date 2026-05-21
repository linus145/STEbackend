from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from .models import AboutUs, Blog, JobOpening, ContactInquiry, ContactSales, Careers
from .serializers import (
    AboutUsSerializer,
    BlogSerializer,
    JobOpeningSerializer,
    CareersSerializer,
    ContactInquirySerializer,
    ContactSalesSerializer,
)


class AboutUsView(APIView):
    permission_classes = [AllowAny]

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
    permission_classes = [AllowAny]
    queryset = Blog.objects.all().order_by("-date")
    serializer_class = BlogSerializer


class BlogDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    queryset = Blog.objects.all()
    serializer_class = BlogSerializer
    lookup_field = "slug"


class JobOpeningListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    queryset = Careers.objects.filter(is_active=True).order_by("-created_at")
    serializer_class = CareersSerializer


class ContactInquiryCreateView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    queryset = ContactInquiry.objects.all()
    serializer_class = ContactInquirySerializer


class ContactSalesCreateView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    queryset = ContactSales.objects.all()
    serializer_class = ContactSalesSerializer
