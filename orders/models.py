from django.conf import settings
from django.db import models


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Oczekuje na płatność"
        PAID = "paid", "Opłacone"
        CANCELLED = "cancelled", "Anulowane"

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders", verbose_name="kupujący"
    )
    status = models.CharField("status", max_length=20, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    stripe_session_id = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "zamówienie"
        verbose_name_plural = "zamówienia"

    def __str__(self):
        return f"Zamówienie #{self.pk}"

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # SET_NULL: usunięcie produktu nie kasuje historii zamówień
    product = models.ForeignKey(
        "products.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items"
    )
    title = models.CharField("nazwa", max_length=120)  # kopia nazwy z chwili zakupu
    unit_price = models.DecimalField("cena jednostkowa", max_digits=10, decimal_places=2)  # kopia ceny
    quantity = models.PositiveIntegerField("ilość")

    class Meta:
        verbose_name = "pozycja zamówienia"
        verbose_name_plural = "pozycje zamówienia"

    def __str__(self):
        return f"{self.title} x{self.quantity}"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

