from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    path("<int:booth_pk>/", views.pos, name="pos"),
    path("<int:booth_pk>/cart/add/", views.cart_add, name="cart_add"),
    path("<int:booth_pk>/cart/remove/<int:goods_pk>/", views.cart_remove, name="cart_remove"),
    path("<int:booth_pk>/checkout/", views.cart_checkout, name="checkout"),
    path("<int:booth_pk>/transactions/", views.transaction_list, name="transaction_list"),
    path("<int:booth_pk>/transactions/<int:pk>/", views.transaction_detail, name="transaction_detail"),
    path("<int:booth_pk>/transactions/<int:pk>/void/", views.transaction_void, name="transaction_void"),
]
