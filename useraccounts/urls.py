from django.urls import path

from .views import RegisterView, LoginView, LogoutView, ProfileView, CookieTokenRefreshView, WsTicketView, PublicProfileView, ChangePasswordView, UpdatePhoneNumberView, GoogleLoginView
app_name = 'useraccounts'

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('google-login/', GoogleLoginView.as_view(), name='google-login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('profile/<uuid:user_id>/', PublicProfileView.as_view(), name='public-profile'),
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('ws-ticket/', WsTicketView.as_view(), name='ws-ticket'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('update-mobile/', UpdatePhoneNumberView.as_view(), name='update-mobile'),
]
