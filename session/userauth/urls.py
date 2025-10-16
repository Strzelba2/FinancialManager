from django.urls import path
from .views import (
    LoginView, LogoutView, RegisterView, VerifySessionView, 
    ActivateAccountView, CryptoBatchView
    )

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('register/', RegisterView.as_view(), name='register'),
    path('verifySession/', VerifySessionView.as_view(), name='verifySession'),
    path('activate/<uidb64>/<token>/', ActivateAccountView.as_view(), name='activate'),
    path("crypto/batch", CryptoBatchView.as_view(), name="crypto-batch"),
]
