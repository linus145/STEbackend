from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserCreditBalanceView, CreditTransactionHistoryView, UserCreditViewSet

router = DefaultRouter()
router.register(r"admin/credits", UserCreditViewSet, basename="admin-credits")

urlpatterns = [
    path("balance/", UserCreditBalanceView.as_view(), name="user-credit-balance"),
    path("history/", CreditTransactionHistoryView.as_view(), name="credit-transaction-history"),
    path("", include(router.urls)),
]

