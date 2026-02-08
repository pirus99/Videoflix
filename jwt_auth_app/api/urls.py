
from django.urls import path
from .views import ActivateAccountView, RegistrationView, LoginView, LogoutView, TokenRefreshView, PasswordResetRequestView, PasswordResetConfirmView

urlpatterns = [
    path('register/', RegistrationView.as_view()),
    path('token/refresh/', TokenRefreshView.as_view()),
    path('login/', LoginView.as_view()),
    path('logout/', LogoutView.as_view()),
    path('activate/<str:token>/', ActivateAccountView.as_view()),
    path('password_reset/', PasswordResetRequestView.as_view()),
    path('password_confirm/<str:reset_token>/', PasswordResetConfirmView.as_view()),
]