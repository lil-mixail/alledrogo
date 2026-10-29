from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.order_list, name="list"),
    path("zloz/", views.checkout, name="checkout"),
    path("<int:pk>/", views.order_detail, name="detail"),
    path("<int:pk>/anuluj/", views.order_cancel, name="cancel"),
    path("<int:pk>/zaplac/", views.order_pay, name="pay"),
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
    path("koszyk/", views.cart, name="cart"),
    path("koszyk/dodaj/<int:product_id>/", views.cart_add, name="cart_add"),
    path("koszyk/zmien/<int:product_id>/", views.cart_update, name="cart_update"),
    path("koszyk/usun/<int:product_id>/", views.cart_remove, name="cart_remove"),
]