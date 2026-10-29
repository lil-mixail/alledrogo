import logging

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from products.models import Product

from . import payments
from .cart import Cart
from .models import Order, OrderItem

logger = logging.getLogger(__name__)


# ---------- koszyk ----------

def cart(request):
    return render(request, "orders/cart.html", {"cart": Cart(request)})


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

    order = Order.objects.create(buyer=request.user)
    for pid, qty in wanted.items():
        product = products[pid]
        OrderItem.objects.create(
            order=order, product=product, title=product.title, unit_price=product.price, quantity=qty
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

    for item in order.items.all():
        if item.product_id:  # oddajemy towar na magazyn
            Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)

    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    payments.expire_session(order.stripe_session_id)
    messages.success(request, "Zamówienie zostało anulowane.")
    return redirect("orders:detail", pk=order.pk)


# ---------- płatności Stripe ----------

@login_required(login_url="accounts:login")
@require_POST
def order_pay(request, pk):
    order = get_object_or_404(Order, pk=pk, buyer=request.user)
    if order.status != Order.Status.NEW:
        messages.error(request, "To zamówienie nie wymaga płatności.")
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