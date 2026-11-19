from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .security import Action, audit


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    audit(Action.LOGIN_SUCCESS, request, user=user)


@receiver(user_login_failed)
def log_login_failure(sender, credentials, request=None, **kwargs):
    # credentials has the password scrubbed by Django; only the username is kept.
    audit(Action.LOGIN_FAILED, request, username=credentials.get("username", "")[:150])


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    if user is not None:
        audit(Action.LOGOUT, request, user=user)
