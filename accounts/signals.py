# zapis logowan do bazy
import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .models import LoginEvent
from .security import get_client_ip, get_user_agent

log = logging.getLogger("alledrogo.security")


def _record(kind, request, user=None, username=""):
    ip = get_client_ip(request)
    LoginEvent.objects.create(
        user=user,
        username=(user.get_username() if user else username)[:150],
        kind=kind,
        ip_address=ip,
        user_agent=get_user_agent(request),
    )
    log.info("auth %s user=%s ip=%s", kind, user.get_username() if user else username, ip)


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    _record(LoginEvent.Kind.SUCCESS, request, user=user)


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user is not None:
        _record(LoginEvent.Kind.LOGOUT, request, user=user)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    _record(LoginEvent.Kind.FAILED, request, username=credentials.get("username", ""))
