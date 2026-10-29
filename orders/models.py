from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models

from .shipping import shipping_total


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Oczekuje na płatność"
        PAID = "paid", "Opłacone"
        CANCELLED = "cancelled", "Anulowane"

    class Delivery(models.TextChoices):
        INPOST = "inpost", "Paczkomat InPost"
        COURIER = "courier", "Kurier"

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders", verbose_name="kupujący"
    )
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    stripe_session_id = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    # dane dostawy; blank=True tylko dla starych zamówień, wymagalność pilnuje DeliveryForm
    delivery_method = models.CharField("sposób dostawy", max_length=20, choices=Delivery.choices, blank=True)
    full_name = models.CharField("imię i nazwisko", max_length=120, blank=True)
    phone = models.CharField("telefon", max_length=20, blank=True)
    parcel_locker = models.CharField("kod paczkomatu", max_length=20, blank=True)  # tylko InPost
    street = models.CharField("ulica i numer", max_length=200, blank=True)  # tylko kurier
    postal_code = models.CharField("kod pocztowy", max_length=6, blank=True)
    city = models.CharField("miejscowość", max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "zamówienie"
        verbose_name_plural = "zamówienia"

    def __str__(self):
        return f"Zamówienie #{self.pk}"

    @staticmethod
    def payment_timeout():
        return timedelta(minutes=settings.ORDER_PAYMENT_TIMEOUT_MINUTES)

    @property
    def payment_deadline(self):
        return self.created_at + self.payment_timeout()

    @property
    def items_total(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def shipping_total(self):
        return shipping_total((item.seller_id, item.shipping_cost) for item in self.items.all())

    @property
    def total(self):
        return self.items_total + self.shipping_total


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # SET_NULL: usunięcie produktu nie kasuje historii zamówień
    product = models.ForeignKey(
        "products.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items"
    )
    title = models.CharField("nazwa", max_length=120)  # kopia nazwy z chwili zakupu
    unit_price = models.DecimalField("cena jednostkowa", max_digits=10, decimal_places=2)  # kopia ceny
    quantity = models.PositiveIntegerField("ilość")
    # kopia kosztu wysyłki produktu z chwili zakupu
    shipping_cost = models.DecimalField("koszt wysyłki", max_digits=8, decimal_places=2, default=Decimal("0.00"))
    # kopia sprzedawcy z chwili zakupu: po usunięciu produktu dalej wiadomo, kto wysyła
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="sold_items", verbose_name="sprzedawca",
    )
    shipped_at = models.DateTimeField("wysłano", null=True, blank=True)

    class Meta:
        verbose_name = "pozycja zamówienia"
        verbose_name_plural = "pozycje zamówienia"

    def __str__(self):
        return f"{self.title} x{self.quantity}"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

