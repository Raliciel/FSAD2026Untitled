from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .security import Action, audit


def role_required(role):
    """Require a logged-in, active user with the given role AND a profile row."""

    def decorator(view):
        @login_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_active or user.role != role or user.profile is None:
                audit(Action.ACCESS_DENIED, request, target=request.path)
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


seller_required = role_required("seller")
staff_required = role_required("staff")
