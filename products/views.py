from django.shortcuts import render


def product_list(request):
    # TODO produkty
    return render(request, "products/product_list.html")
