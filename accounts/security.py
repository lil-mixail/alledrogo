from datetime import timedelta

from django.conf import settings
from django.utils import timezone

# limity logowania
MAX_FAILED_PER_USER_IP = 5    # jeden login z jednego ip
MAX_FAILED_PER_IP = 20        # dowolne loginy z jednego ip (password spraying)
LOCKOUT_WINDOW = timedelta(minutes=15)


def get_client_ip(request):
    if request is None:
        return None
    remote = request.META.get("REMOTE_ADDR")
    proxies = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    if proxies <= 0:
        return remote
    # ALB dopisuje ip klienta na koniec X-Forwarded-For,
    # wczesniejsze wpisy moze wyslac sam klient wiec ich nie bierzemy
    forwarded = [ip.strip() for ip in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if ip.strip()]
    if len(forwarded) >= proxies:
        return forwarded[-proxies]
    return remote


def get_user_agent(request):
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:255]


def is_locked_out(username, ip):
    from .models import LoginEvent

    failed = LoginEvent.objects.filter(
        kind=LoginEvent.Kind.FAILED,
        created_at__gte=timezone.now() - LOCKOUT_WINDOW,
    )
    if ip is None:
        return failed.filter(username__iexact=username, ip_address__isnull=True).count() >= MAX_FAILED_PER_USER_IP

    from_ip = failed.filter(ip_address=ip)
    if from_ip.count() >= MAX_FAILED_PER_IP:
        return True
    return from_ip.filter(username__iexact=username).count() >= MAX_FAILED_PER_USER_IP
