import logging

from django.core.cache import cache

from .services import cancel_expired_orders

logger = logging.getLogger(__name__)

CHECK_EVERY_SECONDS = 60


class CancelExpiredOrdersMiddleware:
    """Przy ruchu na stronie najwyżej raz na minutę anuluje przeterminowane zamówienia.

    Dzięki temu działa to bez crona; na produkcji można dodatkowo uruchamiać
    `manage.py cancel_expired_orders`, żeby anulowanie nie zależało od ruchu.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # cache.add ustawia klucz tylko, gdy go nie ma, więc sprawdzenie rusza raz na minutę
        if cache.add("orders:expired-check", True, CHECK_EVERY_SECONDS):
            try:
                cancel_expired_orders()
            except Exception:
                logger.exception("Automatyczne anulowanie zamówień nie powiodło się")
        return self.get_response(request)
