import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from .middleware import SESSION_KEY
from .models import AuditLog, Seller, Staff
from .validators import PasswordComplexityValidator

User = get_user_model()
PASSWORD = "Str0ng!Pass"


def make_seller(username="seller1"):
    user = User.objects.create_user(username, password=PASSWORD, role=User.Role.SELLER)
    Seller.objects.create(user=user, seller_name=username)
    return user


def make_staff(username="staff1"):
    user = User.objects.create_user(username, password=PASSWORD, role=User.Role.STAFF)
    Staff.objects.create(user=user, staff_name=username)
    return user


class PasswordAndUsernameRulesTests(TestCase):
    def test_complexity_rejects_missing_classes(self):
        validator = PasswordComplexityValidator()
        for weak in ["alllowercase1!", "ALLUPPER1!", "NoSpecial123"]:
            with self.assertRaises(ValidationError):
                validator.validate(weak)
        validator.validate(PASSWORD)

    def test_min_length_is_8(self):
        response = self.client.post(reverse("accounts:register"), {
            "username": "shorty", "seller_name": "S",
            "password1": "Ab1!xyz", "password2": "Ab1!xyz",
        })
        self.assertFalse(User.objects.filter(username="shorty").exists())
        self.assertContains(response, "at least 8 characters")

    def test_username_special_characters_rejected(self):
        for bad in ["a@b", "a_b", "a+b", "a b"]:
            user = User(username=bad)
            with self.assertRaises(ValidationError, msg=bad):
                user.full_clean(exclude=["password"])


class RegistrationTests(TestCase):
    def post(self, **extra):
        data = {
            "username": "newseller", "email": "a@example.com", "seller_name": "New",
            "password1": PASSWORD, "password2": PASSWORD, **extra,
        }
        return self.client.post(reverse("accounts:register"), data)

    def test_register_creates_seller_and_logs_in(self):
        response = self.post()
        self.assertRedirects(response, reverse("booths:register"), fetch_redirect_response=False)
        user = User.objects.get(username="newseller")
        self.assertEqual(user.role, User.Role.SELLER)
        self.assertTrue(Seller.objects.filter(user=user).exists())
        self.assertTrue(user.check_password(PASSWORD))  # stored hashed
        self.assertNotEqual(user.password, PASSWORD)

    def test_role_cannot_be_chosen_by_the_browser(self):
        self.post(role="staff")
        self.assertEqual(User.objects.get(username="newseller").role, User.Role.SELLER)

    def test_mismatched_passwords_rejected(self):
        self.post(password2="Other!Pass1")
        self.assertFalse(User.objects.filter(username="newseller").exists())

    @override_settings(REGISTRATIONS_PER_IP_PER_HOUR=2)
    def test_registration_rate_limited_per_ip(self):
        for i in range(3):
            self.post(username=f"user{i}")
            self.client.logout()
        self.assertEqual(User.objects.filter(username__startswith="user").count(), 2)


class LoginTests(TestCase):
    def setUp(self):
        self.user = make_seller()

    def login(self, password):
        return self.client.post(reverse("accounts:login"), {"username": "seller1", "password": password})

    def test_login_success_is_audited_and_rotates_session(self):
        self.client.get(reverse("accounts:login"))
        old_key = self.client.session.session_key
        self.login(PASSWORD)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertNotEqual(self.client.session.session_key, old_key)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.LOGIN_SUCCESS, user=self.user).exists())

    def test_unknown_user_and_wrong_password_share_one_message(self):
        wrong_password = self.login("Wrong!Pass1").context["form"].non_field_errors()
        unknown_user = self.client.post(
            reverse("accounts:login"), {"username": "nobody", "password": "Wrong!Pass1"}
        ).context["form"].non_field_errors()
        self.assertEqual(wrong_password, unknown_user)

    def test_lockout_after_limit_blocks_even_correct_password(self):
        for _ in range(settings.LOGIN_FAILURE_LIMIT):
            self.login("Wrong!Pass1")
        response = self.login(PASSWORD)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "Too many failed attempts")
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.LOGIN_LOCKED).exists())

    def test_session_lasts_24_hours(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 24 * 60 * 60)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.LOGOUT).exists())


class StaffIdleTimeoutTests(TestCase):
    def test_idle_staff_is_logged_out(self):
        self.client.force_login(make_staff())
        session = self.client.session
        session[SESSION_KEY] = time.time() - settings.STAFF_IDLE_TIMEOUT_SECONDS - 1
        session.save()
        response = self.client.get(reverse("accounts:profile"))
        self.assertRedirects(response, reverse("accounts:login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_idle_seller_is_not_logged_out(self):
        self.client.force_login(make_seller())
        session = self.client.session
        session[SESSION_KEY] = time.time() - settings.STAFF_IDLE_TIMEOUT_SECONDS - 1
        session.save()
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)


class StaffCreateAccountTests(TestCase):
    """Proposal 4.3.9: one test per role for each protected view."""

    def setUp(self):
        self.url = reverse("accounts:staff_create")
        self.data = {
            "username": "newstaff", "staff_name": "New Staff",
            "password1": PASSWORD, "password2": PASSWORD,
        }

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
        self.assertFalse(User.objects.filter(username="newstaff").exists())

    def test_seller_forbidden_and_attempt_logged(self):
        self.client.force_login(make_seller())
        self.assertEqual(self.client.post(self.url, self.data).status_code, 403)
        self.assertFalse(User.objects.filter(username="newstaff").exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.ACCESS_DENIED).exists())

    def test_staff_can_create_staff(self):
        self.client.force_login(make_staff())
        self.client.post(self.url, self.data)
        user = User.objects.get(username="newstaff")
        self.assertEqual(user.role, User.Role.STAFF)
        self.assertFalse(user.is_staff)  # convention staff do not get Django admin access
        self.assertTrue(Staff.objects.filter(user=user).exists())


class AccountEditTests(TestCase):
    def setUp(self):
        self.user = make_seller()
        self.client.force_login(self.user)

    def test_profile_edits_own_account(self):
        self.client.post(reverse("accounts:profile"), {
            "username": "renamed", "email": "", "seller_name": "Renamed",
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "renamed")
        self.assertEqual(self.user.seller.seller_name, "Renamed")

    def test_password_change_requires_current_password(self):
        url = reverse("accounts:password_change")
        new = "N3w!Password"
        self.client.post(url, {"old_password": "Wrong!Pass1", "new_password1": new, "new_password2": new})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

        self.client.post(url, {"old_password": PASSWORD, "new_password1": new, "new_password2": new})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new))
        self.assertIn("_auth_user_id", self.client.session)  # still logged in


class SuperuserTests(TestCase):
    def test_createsuperuser_gets_staff_profile(self):
        admin = User.objects.create_superuser("admin", "a@example.com", PASSWORD)
        self.assertEqual(admin.role, User.Role.STAFF)
        self.assertIsNotNone(admin.profile)
