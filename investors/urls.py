from django.urls import path
from .views import InvestorListView, InvestorDetailView, MyInvestorProfileView

app_name = 'investors'

urlpatterns = [
    path('', InvestorListView.as_view(), name='investor_list'),
    path('me/', MyInvestorProfileView.as_view(), name='my_investor_profile'),
    path('<uuid:investor_id>/', InvestorDetailView.as_view(), name='investor_detail'),
]
