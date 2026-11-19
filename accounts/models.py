from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction

from .validators import IMAGE_VALIDATORS, username_validator


class UserManager(DjangoUserManager):
    @transaction.atomic
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # An administrator also gets a Staff profile so the staff views work for them.
        extra_fields.setdefault("role", User.Role.STAFF)
        user = super().create_superuser(username, email, password, **extra_fields)
        Staff.objects.get_or_create(user=user, defaults={"staff_name": username})
        return user


class User(AbstractUser):
    """Customers are anonymous, so only sellers and staff have accounts."""

    class Role(models.TextChoices):
        SELLER = "seller", "Seller"
        STAFF = "staff", "Staff"

    username = models.CharField(
        max_length=150,
        unique=True,
        validators=[username_validator],
        help_text="Letters, numbers, dots and hyphens only.",
        error_messages={"unique": "A user with that username already exists."},
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.SELLER)

    objects = UserManager()

    @property
    def profile(self):
        try:
            return getattr(self, self.role)
        except ObjectDoesNotExist:
            return None

    @property
    def is_seller(self):
        return self.role == self.Role.SELLER and self.profile is not None

    @property
    def is_convention_staff(self):
        # Not Django's is_staff, which only controls access to the admin site.
        return self.role == self.Role.STAFF and self.profile is not None


class Seller(models.Model):
    seller_id = models.BigAutoField(primary_key=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller"
    )
    seller_name = models.CharField(max_length=100)
    seller_profile_picture = models.ImageField(
        upload_to="sellers/", blank=True, validators=IMAGE_VALIDATORS
    )

    def __str__(self):
        return self.seller_name


class Staff(models.Model):
    staff_id = models.BigAutoField(primary_key=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff"
    )
    staff_name = models.CharField(max_length=100)
    staff_profile_picture = models.ImageField(
        upload_to="staff/", blank=True, validators=IMAGE_VALIDATORS
    )

    class Meta:
        verbose_name_plural = "staff"

    def __str__(self):
        return self.staff_name


class AuditLog(models.Model):
    """Proposal 4.3.9: who did what, when, to which target. Never stores passwords."""

    class Action(models.TextChoices):
        LOGIN_SUCCESS = "login_success", "Login succeeded"
        LOGIN_FAILED = "login_failed", "Login failed"
        LOGIN_LOCKED = "login_locked", "Login blocked by lockout"
        LOGOUT = "logout", "Logout"
        REGISTER = "register", "Seller registered"
        STAFF_CREATED = "staff_created", "Staff account created"
        PASSWORD_CHANGED = "password_changed", "Password changed"
        IDLE_TIMEOUT = "idle_timeout", "Staff session expired"
        ACCESS_DENIED = "access_denied", "Access denied"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    target = models.CharField(max_length=200, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "username", "created_at"]),
            models.Index(fields=["action", "ip_address", "created_at"]),
        ]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.username or '-'} {self.action}"
