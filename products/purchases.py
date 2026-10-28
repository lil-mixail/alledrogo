from django.apps import apps

PAID_STATUS = "paid"


def has_bought(user, product):
    # czy user kupil i oplacil produkt - korzysta z modeli osoby 3 (orders)
    if not user.is_authenticated:
        return False
    try:
        OrderItem = apps.get_model("orders", "OrderItem")
    except LookupError:
        # orders jeszcze nie gotowe
        return False
    return OrderItem.objects.filter(product=product, order__buyer=user, order__status=PAID_STATUS).exists()

