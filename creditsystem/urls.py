from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserCreditBalanceView, CreditTransactionHistoryView, PurchaseCreditsView, VerifyCreditPaymentView, UserCreditViewSet

router = DefaultRouter()
router.register(r"admin/credits", UserCreditViewSet, basename="admin-credits")

urlpatterns = [
    path("balance/", UserCreditBalanceView.as_view(), name="user-credit-balance"),
    path("history/", CreditTransactionHistoryView.as_view(), name="credit-transaction-history"),
    path("purchase/", PurchaseCreditsView.as_view(), name="purchase-credits"),
    path("verify-payment/", VerifyCreditPaymentView.as_view(), name="verify-credit-payment"),
    path("", include(router.urls)),
]

