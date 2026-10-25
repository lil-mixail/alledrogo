# np. @seller_required nad widokiem albo SellerRequiredMixin w klasie
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


def _check(attr):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not getattr(request.user, attr, False):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


seller_required = _check("is_seller")
moderator_required = _check("is_moderator")
admin_required = _check("is_admin_role")


class _RoleMixin(LoginRequiredMixin):
    required_attr = None

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not getattr(request.user, self.required_attr, False):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class SellerRequiredMixin(_RoleMixin):
    required_attr = "is_seller"


class ModeratorRequiredMixin(_RoleMixin):
    required_attr = "is_moderator"


class AdminRequiredMixin(_RoleMixin):
    required_attr = "is_admin_role"
