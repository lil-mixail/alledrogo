from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    path("", views.product_list, name="list"),
    path("moje/", views.my_products, name="mine"),
    path("dodaj/", views.product_create, name="create"),
    path("<int:pk>/", views.product_detail, name="detail"),
    path("<int:pk>/edytuj/", views.product_edit, name="edit"),
    path("<int:pk>/usun/", views.product_delete, name="delete"),
    path("<int:pk>/zdjecia/dodaj/", views.image_add, name="image_add"),
    path("zdjecia/<int:pk>/usun/", views.image_delete, name="image_delete"),
    path("<int:pk>/opinie/dodaj/", views.comment_add, name="comment_add"),
    path("opinie/<int:pk>/usun/", views.comment_delete, name="comment_delete"),
    path("<int:pk>/napisz/", views.conversation_start, name="conversation_start"),
    path("wiadomosci/", views.conversation_list, name="conversations"),
    path("wiadomosci/<int:pk>/", views.conversation_detail, name="conversation"),
    path("wiadomosci/<int:pk>/nowe/", views.conversation_messages, name="conversation_messages"),
]

