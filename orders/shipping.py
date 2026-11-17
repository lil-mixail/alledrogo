from decimal import Decimal


def shipping_total(items):
    """items: pary (id_sprzedawcy, koszt wysyłki produktu).

    Każdy sprzedawca wysyła jedną paczkę, więc liczymy najwyższy koszt
    spośród jego produktów, a nie sumę za każdą sztukę.
    """
    per_seller = {}
    for seller_id, cost in items:
        per_seller[seller_id] = max(cost, per_seller.get(seller_id, Decimal("0")))
    return sum(per_seller.values(), Decimal("0"))
