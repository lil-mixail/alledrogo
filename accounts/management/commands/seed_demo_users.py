# konta testowe: python manage.py seed_demo_users
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User

DEMO_PASSWORD = "Alledrogo!2026"

DEMO_USERS = [
    ("admin", "admin@alledrogo.local", User.Role.ADMIN),
    ("moderator", "moderator@alledrogo.local", User.Role.MODERATOR),
    ("sprzedawca", "sprzedawca@alledrogo.local", User.Role.SELLER),
    ("klient", "klient@alledrogo.local", User.Role.CUSTOMER),
]


class Command(BaseCommand):
    help = "Tworzy konta demo (tylko DEBUG=True)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Konta demo można tworzyć tylko lokalnie (DJANGO_DEBUG=True).")
        for username, email, role in DEMO_USERS:
            user, created = User.objects.get_or_create(username=username, defaults={"email": email})
            user.role = role
            user.is_staff = role in (User.Role.ADMIN, User.Role.MODERATOR)
            user.is_superuser = role == User.Role.ADMIN
            user.set_password(DEMO_PASSWORD)
            user.save()
            self.stdout.write(f"{'utworzono' if created else 'zaktualizowano'}: {username} ({role})")
        self.stdout.write(self.style.SUCCESS(f"Hasło dla wszystkich kont demo: {DEMO_PASSWORD}"))
