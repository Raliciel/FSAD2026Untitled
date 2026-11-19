import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect

from .security import Action, audit

SESSION_KEY = "last_activity"


class StaffIdleTimeoutMiddleware:
    """Proposal 4.3.4: staff sessions end after a short idle time (sellers keep 24 h)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and user.role == user.Role.STAFF:
            now = time.time()
            last = request.session.get(SESSION_KEY, now)
            if now - last > settings.STAFF_IDLE_TIMEOUT_SECONDS:
                audit(Action.IDLE_TIMEOUT, request, user=user)
                logout(request)
                messages.info(request, "You were logged out after a period of inactivity.")
                return redirect(settings.LOGIN_URL)
            request.session[SESSION_KEY] = now
        return self.get_response(request)
