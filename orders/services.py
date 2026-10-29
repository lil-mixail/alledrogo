import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from products.models import Product

from . import payments
from .models import Order

logger = logging.getLogger(__name__)


def cancel_order(order):
    """Anuluje nieopłacone zamówienie i oddaje towar na magazyn.

    Zamówienie musi być zablokowane (select_for_update) i mieć status NEW.
    Zwraca False, jeśli nie anulowano, bo płatność zdążyła przejść albo Stripe nie odpowiada.
    """
    if not payments.close_session(order):
        return False

    for item in order.items.all():
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)

    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    return True


def cancel_expired_orders():
    """Anuluje zamówienia, których nie opłacono w wyznaczonym czasie. Zwraca liczbę anulowanych."""
    overdue = Order.objects.filter(
        status=Order.Status.NEW, created_at__lt=timezone.now() - Order.payment_timeout()
    ).values_list("pk", flat=True)

    cancelled = 0
    for pk in list(overdue):
        try:
            # każde zamówienie osobno: błąd jednego nie blokuje pozostałych
            with transaction.atomic():
                order = Order.objects.select_for_update().filter(pk=pk, status=Order.Status.NEW).first()
                if order is not None and cancel_order(order):
                    cancelled += 1
                    logger.info("Anulowano nieopłacone zamówienie #%s", pk)
        except Exception:
            logger.exception("Nie udało się anulować zamówienia #%s", pk)
    return cancelled
