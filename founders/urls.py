from django.urls import path
from .views import FounderListView, FounderDetailView, MyFounderProfileView

app_name = 'founders'

urlpatterns = [
    path('', FounderListView.as_view(), name='founder_list'),
    path('me/', MyFounderProfileView.as_view(), name='my_founder_profile'),
    path('<uuid:founder_id>/', FounderDetailView.as_view(), name='founder_detail'),
]
