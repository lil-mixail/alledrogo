from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Klient"
        SELLER = "seller", "Sprzedawca"
        MODERATOR = "moderator", "Moderator"
        ADMIN = "admin", "Administrator"

    email = models.EmailField("e-mail", unique=True)
    role = models.CharField("rola", max_length=20, choices=Role.choices, default=Role.CUSTOMER)

    class Meta:
        verbose_name = "użytkownik"
        verbose_name_plural = "użytkownicy"

    def save(self, *args, **kwargs):
        # superuser = admin
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    # sprawdzanie rol
    @property
    def is_admin_role(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def is_moderator(self):
        return self.is_admin_role or self.role == self.Role.MODERATOR

    @property
    def is_seller(self):
        return self.is_admin_role or self.role == self.Role.SELLER


class LoginEvent(models.Model):
    # historia logowan
    class Kind(models.TextChoices):
        SUCCESS = "success", "Udane logowanie"
        FAILED = "failed", "Nieudane logowanie"
        LOGOUT = "logout", "Wylogowanie"
        LOCKED = "locked", "Zablokowana próba"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    username = models.CharField(max_length=150, db_index=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "zdarzenie logowania"
        verbose_name_plural = "zdarzenia logowania"

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.username} {self.kind}"
