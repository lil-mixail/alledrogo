from products.models import Product

CART_SESSION_KEY = "cart"


class Cart:
    """Koszyk w sesji: {id_produktu: ilość}. Ceny zawsze z bazy."""

    def __init__(self, request):
        self.session = request.session
        self.cart = self.session.setdefault(CART_SESSION_KEY, {})

    def add(self, product, quantity=1, override=False):
        pid = str(product.pk)
        new_qty = quantity if override else self.cart.get(pid, 0) + quantity
        new_qty = min(new_qty, product.stock)  # nie więcej niż na stanie
        if new_qty > 0:
            self.cart[pid] = new_qty
        else:
            self.cart.pop(pid, None)
        self.session.modified = True

    def remove(self, product):
        self.cart.pop(str(product.pk), None)
        self.session.modified = True

    def clear(self):
        self.session[CART_SESSION_KEY] = {}
        self.session.modified = True

    def __iter__(self):
        products = Product.objects.filter(pk__in=self.cart.keys())
        for product in products:
            qty = self.cart[str(product.pk)]
            yield {"product": product, "quantity": qty, "subtotal": product.price * qty}

    def __len__(self):
        return sum(self.cart.values())

    @property
    def total_price(self):
        return sum(item["subtotal"] for item in self)