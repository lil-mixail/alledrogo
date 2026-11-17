import logging

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.permissions import seller_required
from products.models import Product

from . import payments
from .cart import Cart
from .forms import DeliveryForm
from .models import Order, OrderItem
from .services import cancel_order
from .shipping import shipping_total

logger = logging.getLogger(__name__)


# ---------- koszyk ----------

def _render_cart(request, delivery_form=None, status=200):
    if delivery_form is None:
        initial = {}
        if request.user.is_authenticated:
            initial["full_name"] = request.user.get_full_name()
        delivery_form = DeliveryForm(initial=initial)
    return render(
        request, "orders/cart.html", {"cart": Cart(request), "delivery_form": delivery_form}, status=status
    )


def cart(request):
    return _render_cart(request)


def _parse_quantity(value, default=1):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)

    if product.seller_id == request.user.pk:
        messages.error(request, "Nie możesz kupić własnego produktu.")
    elif product.stock < 1:
        messages.error(request, "Ten produkt jest niedostępny.")
    else:
        quantity = max(1, _parse_quantity(request.POST.get("quantity")))
        Cart(request).add(product, quantity)
        messages.success(request, f"Dodano do koszyka: {product.title}")

    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, request.get_host()):
        return redirect(next_url)
    return redirect("orders:cart")


@require_POST
def cart_update(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    quantity = _parse_quantity(request.POST.get("quantity"), default=1)
    Cart(request).add(product, quantity, override=True)  # 0 usuwa pozycję
    return redirect("orders:cart")


@require_POST
def cart_remove(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    Cart(request).remove(product)
    return redirect("orders:cart")


# ---------- zamówienia ----------

@login_required(login_url="accounts:login")
@require_POST
@transaction.atomic
def checkout(request):
    cart_obj = Cart(request)
    if not len(cart_obj):
        messages.error(request, "Twój koszyk jest pusty.")
        return redirect("orders:cart")

    delivery_form = DeliveryForm(request.POST)
    if not delivery_form.is_valid():
        messages.error(request, "Uzupełnij poprawnie dane dostawy.")
        return _render_cart(request, delivery_form, status=400)

    wanted = {int(pid): qty for pid, qty in cart_obj.cart.items()}
    # blokujemy wiersze produktów, żeby dwie osoby nie kupiły tej samej ostatniej sztuki
    products = {p.pk: p for p in Product.objects.select_for_update().filter(pk__in=wanted)}

    errors = []
    for pid, qty in wanted.items():
        product = products.get(pid)
        if product is None:
            errors.append("Jeden z produktów w koszyku został usunięty i wypadł z koszyka.")
            cart_obj.cart.pop(str(pid), None)  # inaczej użytkownik nie mógłby go usunąć
            request.session.modified = True
        elif not product.is_active:
            errors.append(f"{product.title}: produkt jest już niedostępny, usuń go z koszyka.")
        elif product.seller_id == request.user.pk:
            errors.append(f"{product.title}: nie możesz kupić własnego produktu.")
        elif product.stock < qty:
            errors.append(f"{product.title}: dostępne tylko {product.stock} szt.")

    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect("orders:cart")

    order = delivery_form.save(commit=False)
    order.buyer = request.user
    order.save()
    for pid, qty in wanted.items():
        product = products[pid]
        OrderItem.objects.create(
            order=order, product=product, seller_id=product.seller_id,
            title=product.title, unit_price=product.price, quantity=qty, shipping_cost=product.shipping_cost,
        )
        product.stock -= qty
        product.save(update_fields=["stock"])

    cart_obj.clear()
    messages.success(request, "Zamówienie zostało złożone.")
    return redirect("orders:detail", pk=order.pk)


@login_required(login_url="accounts:login")
def order_list(request):
    orders = Order.objects.filter(buyer=request.user).prefetch_related("items")
    return render(request, "orders/order_list.html", {"orders": orders})


@login_required(login_url="accounts:login")
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related("items"), pk=pk, buyer=request.user)

    # powrót ze Stripe: sprawdzamy płatność u źródła (webhook robi to samo niezależnie)
    session_id = request.GET.get("session_id")
    if order.status == Order.Status.NEW and session_id and session_id == order.stripe_session_id:
        try:
            paid = payments.sync_order_payment(order)
        except stripe.StripeError:
            logger.exception("Stripe: nie udało się sprawdzić płatności zamówienia #%s", order.pk)
            paid = False
        if paid:
            messages.success(request, "Płatność przyjęta, dziękujemy!")
            return redirect("orders:detail", pk=order.pk)

    return render(request, "orders/order_detail.html", {"order": order})


@login_required(login_url="accounts:login")
@require_POST
@transaction.atomic
def order_cancel(request, pk):
    order = get_object_or_404(Order.objects.select_for_update(), pk=pk, buyer=request.user)
    if order.status != Order.Status.NEW:
        messages.error(request, "Tego zamówienia nie można już anulować.")
        return redirect("orders:detail", pk=order.pk)

    if not cancel_order(order):
        order.refresh_from_db()  # mark_paid mógł właśnie zmienić status
        if order.status == Order.Status.PAID:
            messages.info(request, "Zamówienie zostało już opłacone, nie można go anulować.")
        else:
            messages.error(request, "Nie udało się połączyć z operatorem płatności. Spróbuj ponownie.")
        return redirect("orders:detail", pk=order.pk)
    messages.success(request, "Zamówienie zostało anulowane.")
    return redirect("orders:detail", pk=order.pk)


# ---------- panel sprzedawcy ----------

@seller_required
def seller_orders(request):
    # tylko opłacone: nieopłaconych nie wysyłamy, anulowanych też nie
    my_items = OrderItem.objects.filter(seller=request.user)
    orders = (
        Order.objects.filter(status=Order.Status.PAID, items__seller=request.user)
        .distinct()
        .prefetch_related(Prefetch("items", queryset=my_items, to_attr="my_items"))
        .select_related("buyer")
        .order_by("paid_at")
    )
    to_ship, shipped = [], []
    for order in orders:
        order.my_shipping = shipping_total((i.seller_id, i.shipping_cost) for i in order.my_items)
        order.my_total = sum(item.subtotal for item in order.my_items) + order.my_shipping
        order.my_shipped_at = max((i.shipped_at for i in order.my_items if i.shipped_at), default=None)
        if all(item.shipped_at for item in order.my_items):
            shipped.append(order)
        else:
            to_ship.append(order)
    shipped.sort(key=lambda o: o.my_shipped_at, reverse=True)
    return render(request, "orders/seller_orders.html", {"to_ship": to_ship, "shipped": shipped})


@seller_required
@require_POST
def seller_mark_shipped(request, pk):
    order = get_object_or_404(
        Order.objects.filter(status=Order.Status.PAID, items__seller=request.user).distinct(), pk=pk
    )
    # oznaczamy tylko swoje pozycje; inni sprzedawcy z tego zamówienia wysyłają osobno
    updated = OrderItem.objects.filter(order=order, seller=request.user, shipped_at__isnull=True).update(
        shipped_at=timezone.now()
    )
    if updated:
        messages.success(request, f"Zamówienie #{order.pk} oznaczone jako wysłane.")
    else:
        messages.info(request, f"Zamówienie #{order.pk} było już oznaczone jako wysłane.")
    return redirect("orders:seller_orders")


# ---------- płatności Stripe ----------

@login_required(login_url="accounts:login")
@require_POST
def order_pay(request, pk):
    order = get_object_or_404(Order, pk=pk, buyer=request.user)
    if order.status != Order.Status.NEW:
        messages.error(request, "To zamówienie nie wymaga płatności.")
        return redirect("orders:detail", pk=order.pk)
    if timezone.now() >= order.payment_deadline:
        messages.error(request, "Czas na opłacenie zamówienia minął, zostanie ono anulowane.")
        return redirect("orders:detail", pk=order.pk)
    if not settings.STRIPE_SECRET_KEY:
        messages.error(request, "Płatności nie są skonfigurowane.")
        return redirect("orders:detail", pk=order.pk)

    try:
        url = payments.get_checkout_url(request, order)
    except stripe.StripeError:
        logger.exception("Stripe: nie udało się utworzyć płatności dla zamówienia #%s", order.pk)
        messages.error(request, "Nie udało się połączyć z operatorem płatności. Spróbuj ponownie.")
        return redirect("orders:detail", pk=order.pk)
    return redirect(url)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    try:
        event = stripe.Webhook.construct_event(
            request.body, request.META.get("HTTP_STRIPE_SIGNATURE", ""), settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponse(status=400)

    if event.type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        payments.mark_paid(event.data.object)
    return HttpResponse(status=200)