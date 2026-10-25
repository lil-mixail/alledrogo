from django.shortcuts import render


def cart(request):
    # TODO koszyk
    return render(request, "orders/cart.html")
