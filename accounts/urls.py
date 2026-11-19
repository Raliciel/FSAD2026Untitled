from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),  # POST only
    path("profile/", views.profile_edit, name="profile"),
    path("password/", views.PasswordChangeView.as_view(), name="password_change"),
    path("staff/new/", views.staff_create_account, name="staff_create"),
    path("users/", views.user_list, name="user_list"),
    path("users/<int:pk>/edit/", views.user_edit, name="user_edit"),
]
