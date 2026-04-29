from django.urls import path
from .views import AboutUsView, BlogListView, BlogDetailView, JobOpeningListView, ContactInquiryCreateView

urlpatterns = [
    path('aboutus/', AboutUsView.as_view(), name='aboutus'),
    path('careers/', JobOpeningListView.as_view(), name='careers'),
    path('blogs/', BlogListView.as_view(), name='blogs'),
    path('blogs/<slug:slug>/', BlogDetailView.as_view(), name='blog-detail'),
    path('contactus/', ContactInquiryCreateView.as_view(), name='contactus'),
]