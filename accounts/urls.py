from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("rejestracja/", views.register, name="register"),
    path("logowanie/", views.LoginView.as_view(), name="login"),
    # tylko POST
    path("wyloguj/", auth_views.LogoutView.as_view(), name="logout"),
    path("profil/", views.profile, name="profile"),
    path("haslo/", views.PasswordChangeView.as_view(), name="password_change"),
]
