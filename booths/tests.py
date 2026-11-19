from django.test import TestCase
from django.urls import reverse

from accounts.models import AuditLog
from accounts.tests import make_seller, make_staff

from .models import BankAccount, Booth, SellerBooth


def make_booth(seller_user, name="Booth A", table=1, **extra):
    bank, _ = BankAccount.objects.get_or_create(
        bank_account_number=f"100000{table:04d}", defaults={"bank_name": "KBank", "holder_name": name}
    )
    booth = Booth.objects.create(booth_name=name, table_number=table, bank_account=bank, **extra)
    SellerBooth.objects.create(booth=booth, seller=seller_user.seller)
    return booth


class BoothOwnershipTests(TestCase):
    """A seller may only open booths they belong to; others get 403 and an audit entry."""

    def setUp(self):
        self.owner = make_seller("owner")
        self.other = make_seller("other")
        self.booth = make_booth(self.owner)

    def assert_forbidden(self, url):
        self.client.force_login(self.other)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Access denied", status_code=403)
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.ACCESS_DENIED, target=url).exists()
        )

    def test_other_seller_cannot_edit_booth(self):
        self.assert_forbidden(reverse("booths:edit", args=[self.booth.pk]))

    def test_other_seller_cannot_open_goods_list(self):
        self.assert_forbidden(reverse("catalog:submit_goods", args=[self.booth.pk]))

    def test_other_seller_cannot_change_booth(self):
        self.client.force_login(self.other)
        url = reverse("booths:edit", args=[self.booth.pk])
        self.client.post(url, {"booth_name": "Hijacked", "table_number": 9})
        self.booth.refresh_from_db()
        self.assertEqual(self.booth.booth_name, "Booth A")

    def test_owner_can_open_booth(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("booths:edit", args=[self.booth.pk])).status_code, 200)

    def test_staff_cannot_use_seller_views(self):
        self.client.force_login(make_staff())
        self.assertEqual(self.client.get(reverse("booths:edit", args=[self.booth.pk])).status_code, 403)

    def test_missing_booth_is_404(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("booths:edit", args=[999])).status_code, 404)
