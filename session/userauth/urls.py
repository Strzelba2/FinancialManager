from django.urls import path
from .views import (
    LoginView, LogoutView, RegisterView, VerifySessionView,
    ActivateAccountView, CryptoBatchView, SetWalletUserIdView,
    TwoFactorDisableView, TwoFactorEnableView, TwoFactorSetupView,
    TwoFactorStatusView, TwoFactorVerifyView,
)
from .views_health import healthz, readyz

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('register/', RegisterView.as_view(), name='register'),
    path('verifySession/', VerifySessionView.as_view(), name='verifySession'),
    path('two-factor/status/', TwoFactorStatusView.as_view(), name='two-factor-status'),
    path('two-factor/setup/', TwoFactorSetupView.as_view(), name='two-factor-setup'),
    path('two-factor/enable/', TwoFactorEnableView.as_view(), name='two-factor-enable'),
    path('two-factor/disable/', TwoFactorDisableView.as_view(), name='two-factor-disable'),
    path('two-factor/verify/', TwoFactorVerifyView.as_view(), name='two-factor-verify'),
    path('activate/<uidb64>/<token>/', ActivateAccountView.as_view(), name='activate'),
    path("crypto/batch", CryptoBatchView.as_view(), name="crypto-batch"),
    path("wallet-user-id/", SetWalletUserIdView.as_view(), name="wallet-user-id"),
    path("healthz", healthz),
    path("readyz", readyz),
]
