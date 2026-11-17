# anulowanie nieopłaconych zamówień: python manage.py cancel_expired_orders (np. z crona co 5 minut)
from django.core.management.base import BaseCommand

from orders.services import cancel_expired_orders


class Command(BaseCommand):
    help = "Anuluje zamówienia nieopłacone w wyznaczonym czasie i oddaje towar na magazyn."

    def handle(self, *args, **options):
        count = cancel_expired_orders()
        self.stdout.write(self.style.SUCCESS(f"Anulowano zamówień: {count}"))
