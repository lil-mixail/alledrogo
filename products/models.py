import uuid
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse


def product_image_path(instance, filename):
    # losowa nazwa pliku - nie ufamy nazwie od uzytkownika
    ext = Path(filename).suffix.lower()
    return f"products/{instance.product_id}/{uuid.uuid4().hex}{ext}"


class Product(models.Model):
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="products", verbose_name="sprzedawca"
    )
    title = models.CharField("nazwa", max_length=120)
    description = models.TextField("opis", max_length=5000)
    price = models.DecimalField(
        "cena (zł)", max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    stock = models.PositiveIntegerField("dostępna ilość", default=1)
    is_active = models.BooleanField("widoczny w sklepie", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "produkt"
        verbose_name_plural = "produkty"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("products:detail", args=[self.pk])


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField("zdjęcie", upload_to=product_image_path)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "zdjęcie produktu"
        verbose_name_plural = "zdjęcia produktów"

    def __str__(self):
        return f"{self.product} – {self.image.name}"


@receiver(post_delete, sender=ProductImage)
def delete_image_file(sender, instance, **kwargs):
    # razem z rekordem kasujemy plik z dysku
    instance.image.delete(save=False)


class Comment(models.Model):
    # opinia - tylko od osoby, ktora kupila produkt (sprawdzane w widoku)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="product_comments")
    rating = models.PositiveSmallIntegerField("ocena", validators=[MinValueValidator(1), MaxValueValidator(5)])
    body = models.TextField("treść", max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["product", "author"], name="one_comment_per_product")]
        verbose_name = "opinia"
        verbose_name_plural = "opinie"

    def __str__(self):
        return f"{self.author} o {self.product} ({self.rating}/5)"


class Conversation(models.Model):
    # jedna rozmowa na pare (produkt, kupujacy)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="conversations")
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations_as_buyer"
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations_as_seller"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [models.UniqueConstraint(fields=["product", "buyer"], name="one_conversation_per_buyer")]
        verbose_name = "rozmowa"
        verbose_name_plural = "rozmowy"

    def __str__(self):
        return f"{self.product} – {self.buyer}"

    def has_participant(self, user):
        return user.is_authenticated and user.pk in (self.buyer_id, self.seller_id)

    def other_party(self, user):
        return self.seller if user.pk == self.buyer_id else self.buyer


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField("wiadomość", max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "wiadomość"
        verbose_name_plural = "wiadomości"

