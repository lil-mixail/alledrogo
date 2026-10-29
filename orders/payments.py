import logging
from datetime import timedelta
from decimal import Decimal

import stripe
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import Order

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


def to_grosze(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())


def _line_item(name, amount, quantity=1):
    return {
        "quantity": quantity,
        "price_data": {"currency": "pln", "unit_amount": to_grosze(amount), "product_data": {"name": name}},
    }


def create_checkout_session(request, order):
    detail_url = request.build_absolute_uri(reverse("orders:detail", args=[order.pk]))
    line_items = [_line_item(item.title, item.unit_price, item.quantity) for item in order.items.all()]
    if order.shipping_total:
        line_items.append(_line_item("Wysyłka", order.shipping_total))
    session = stripe.checkout.Session.create(
        mode="payment",
        client_reference_id=str(order.pk),
        metadata={"order_id": str(order.pk)},
        line_items=line_items,
        # Stripe wymaga min. 30 minut; po terminie i tak zamykamy sesję przy anulowaniu
        expires_at=int(max(order.payment_deadline, timezone.now() + timedelta(minutes=31)).timestamp()),
        success_url=detail_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=detail_url,
    )
    order.stripe_session_id = session.id
    order.save(update_fields=["stripe_session_id", "updated_at"])
    return session


def get_checkout_url(request, order):
    """Wraca do otwartej sesji, jeśli już jest, inaczej tworzy nową."""
    if order.stripe_session_id:
        existing = stripe.checkout.Session.retrieve(order.stripe_session_id)
        if existing.status == "open":
            return existing.url
    return create_checkout_session(request, order).url


def mark_paid(session):
    """Oznacza zamówienie jako opłacone, jeśli sesja Stripe faktycznie jest opłacona."""
    if session.payment_status != "paid":
        return False

    order_id = session.client_reference_id
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(pk=order_id).first()
        if order is None:
            logger.warning("Stripe: płatność dla nieistniejącego zamówienia %s", order_id)
            return False
        if order.status == Order.Status.PAID:
            return True
        if order.status != Order.Status.NEW:
            logger.error("Stripe: opłacono zamówienie #%s w statusie %s, potrzebny ręczny zwrot", order.pk, order.status)
            return False
        if session.amount_total != to_grosze(order.total):
            logger.error("Stripe: kwota płatności nie zgadza się z zamówieniem #%s", order.pk)
            return False

        order.status = Order.Status.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at", "updated_at"])
    return True


def sync_order_payment(order):
    """Pyta Stripe o stan sesji tego zamówienia i w razie opłacenia aktualizuje status."""
    if not order.stripe_session_id:
        return False
    session = stripe.checkout.Session.retrieve(order.stripe_session_id)
    return mark_paid(session)


def close_session(order):
    """Zamyka sesję płatności przed anulowaniem zamówienia, żeby nie dało się już zapłacić.

    Zwraca False, jeśli zamówienia nie wolno anulować: klient zdążył zapłacić
    (wtedy oznaczamy je jako opłacone) albo Stripe nie odpowiada.
    """
    if not order.stripe_session_id:
        return True
    try:
        stripe.checkout.Session.expire(order.stripe_session_id)
        return True
    except stripe.StripeError:
        pass  # sesja już zamknięta: wygasła albo została opłacona, sprawdzamy która
    try:
        session = stripe.checkout.Session.retrieve(order.stripe_session_id)
    except stripe.StripeError:
        logger.exception("Stripe: nie udało się sprawdzić sesji zamówienia #%s", order.pk)
        return False
    if session.payment_status == "paid":
        mark_paid(session)
        return False
    return True