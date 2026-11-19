from django.urls import path

from . import views

app_name = "booths"

urlpatterns = [
    path("mine/", views.my_booths, name="my_booths"),
    path("register/", views.booth_register, name="register"),
    path("<int:pk>/edit/", views.booth_edit, name="edit"),
    path("review/", views.review_list, name="review_list"),
    path("review/<int:pk>/", views.booth_review, name="review"),
]
