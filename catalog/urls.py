from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.goods_list, name="goods_list"),
    path("goods/<int:pk>/", views.goods_detail, name="goods_detail"),
    path("sell/<int:booth_pk>/goods/", views.submit_goods, name="submit_goods"),
    path("staff/booths/<int:booth_pk>/goods/", views.booth_goods_review, name="booth_goods_review"),
    path(
        "staff/booths/<int:booth_pk>/goods/<int:goods_pk>/review/",
        views.goods_review, name="goods_review",
    ),
]
