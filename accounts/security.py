from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import AuditLog

Action = AuditLog.Action


def client_ip(request):
    # REMOTE_ADDR only: X-Forwarded-For is client-controlled unless a trusted proxy rewrites it.
    return request.META.get("REMOTE_ADDR") if request else None


def audit(action, request=None, user=None, username="", target=""):
    if user is None and request is not None and request.user.is_authenticated:
        user = request.user
    AuditLog.objects.create(
        action=action,
        user=user,
        username=username or (user.get_username() if user else ""),
        target=str(target)[:200],
        ip_address=client_ip(request),
    )


def _recent(action, minutes):
    return AuditLog.objects.filter(
        action=action, created_at__gte=timezone.now() - timedelta(minutes=minutes)
    )


def is_locked_out(username, ip):
    """UC04-01 ext. 5a: too many recent failures for this username or this address."""
    failures = _recent(Action.LOGIN_FAILED, settings.LOGIN_LOCKOUT_MINUTES)
    if username and failures.filter(username__iexact=username).count() >= settings.LOGIN_FAILURE_LIMIT:
        return True
    return bool(ip) and failures.filter(ip_address=ip).count() >= settings.LOGIN_IP_FAILURE_LIMIT


def registration_rate_exceeded(ip):
    if not ip:
        return False
    return _recent(Action.REGISTER, 60).filter(ip_address=ip).count() >= (
        settings.REGISTRATIONS_PER_IP_PER_HOUR
    )
