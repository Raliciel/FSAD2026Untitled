from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from accounts.models import Seller, User
from accounts.tests import make_seller
from booths.models import BankAccount, Booth, VerificationStatus
from booths.tests import make_booth
from catalog.models import Fandom, Goods, GoodsList, MerchType

from .models import Cart, Transaction, TransactionItem
from .services import SaleError, add_to_cart, checkout, open_cart, void_transaction

APPROVED = VerificationStatus.APPROVED
CASH = Transaction.PaymentMethod.CASH


SEED_PASSWORD = "Seed!Test9"


class SeedDemoTests(TestCase):
    # The test runner forces DEBUG off, hence force=True.
    def seed(self, **options):
        call_command("seed_demo", stdout=StringIO(), password=SEED_PASSWORD, force=True, **options)

    def counts(self):
        return [m.objects.count() for m in (User, Booth, Goods, Transaction, TransactionItem, GoodsList)]

    def test_seed_is_idempotent_and_consistent(self):
        self.seed()
        first = self.counts()
        self.seed()
        self.assertEqual(self.counts(), first)
        self.assertEqual(first[:4], [3, 3, 13, 6])
        # Stock reflects completed sales only: 15 - 2 - 1 Paimon stands sold, the voided sale restored.
        self.assertEqual(Goods.objects.get(goods_name__startswith="Paimon").stock, 12)
        self.assertEqual(Goods.objects.get(goods_name="Raiden Shogun Keychain").stock, 25)
        self.assertEqual(Transaction.objects.filter(status=Transaction.Status.VOIDED).count(), 1)

    def test_seeded_logins_work(self):
        self.seed()
        for username in ("staff.nok", "mint.seller", "ploy.seller"):
            with self.subTest(username=username):
                self.assertTrue(self.client.login(username=username, password=SEED_PASSWORD))

    def test_staff_is_admin_only_with_flag(self):
        self.seed()
        self.assertFalse(User.objects.get(username="staff.nok").is_superuser)
        self.seed(admin=True)
        self.assertTrue(User.objects.get(username="staff.nok").is_superuser)

    def test_refuses_without_password_or_with_weak_one(self):
        with patch.dict("os.environ", {"DEMO_PASSWORD": ""}):
            with self.assertRaisesMessage(CommandError, "No demo password set"):
                call_command("seed_demo", stdout=StringIO(), force=True)
        with self.assertRaisesMessage(CommandError, "Demo password rejected"):
            call_command("seed_demo", stdout=StringIO(), password="short", force=True)
        self.assertFalse(User.objects.exists())

    def test_refuses_when_debug_is_off(self):
        with self.assertRaisesMessage(CommandError, "DJANGO_DEBUG is false"):
            call_command("seed_demo", stdout=StringIO(), password=SEED_PASSWORD)
        self.assertFalse(User.objects.exists())

    def test_seeded_landing_page_has_content(self):
        self.seed()
        response = self.client.get(reverse("catalog:goods_list"))
        self.assertEqual(len(response.context["recommended"]), 4)
        self.assertContains(response, "Paimon Emergency Food Acrylic Stand")
        self.assertNotContains(response, "Isagi")  # pending booth stays hidden


class POSFixture(TestCase):
    def setUp(self):
        self.user = make_seller("owner")
        self.seller = self.user.seller
        self.booth = make_booth(self.user, verification=APPROVED)
        self.fandom = Fandom.objects.create(fandom="Genshin Impact")
        self.type = MerchType.objects.create(name="Acrylic stand")
        self.stand = self.make_goods("Stand", "120.00", 10, APPROVED)
        self.pending = self.make_goods("Pending item", "80.00", 10, VerificationStatus.PENDING)

    def make_goods(self, name, price, stock, verification, booth=None):
        goods = Goods.objects.create(
            goods_name=name, goods_price=Decimal(price), stock=stock, verification=verification,
            fandom=self.fandom, merch_type=self.type,
        )
        GoodsList.objects.create(booth=booth or self.booth, goods=goods)
        return goods

    def sell(self, goods, qty):
        cart = open_cart(self.booth, self.seller)
        add_to_cart(cart, goods.pk, qty)
        return checkout(cart, self.seller, CASH)


class CheckoutAndVoidTests(POSFixture):
    def test_checkout_reduces_stock_and_records_prices(self):
        tx = self.sell(self.stand, 3)
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.stock, 7)
        self.assertEqual(tx.total_amount, Decimal("360.00"))
        self.assertEqual(tx.items.get().goods_name, "Stand")
        self.assertEqual(tx.cart.status, Cart.Status.CHECKED_OUT)

    def test_void_restores_stock(self):
        tx = self.sell(self.stand, 3)
        void_transaction(tx, self.seller)
        self.stand.refresh_from_db()
        tx.refresh_from_db()
        self.assertEqual(self.stand.stock, 10)
        self.assertEqual(tx.status, Transaction.Status.VOIDED)
        self.assertEqual(tx.voided_by, self.seller)
        self.assertIsNotNone(tx.voided_at)

    def test_void_twice_does_not_add_stock_twice(self):
        tx = self.sell(self.stand, 3)
        void_transaction(tx, self.seller)
        with self.assertRaises(SaleError):
            void_transaction(tx, self.seller)
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.stock, 10)

    def test_stock_change_keeps_goods_approved(self):
        self.sell(self.stand, 1)
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.verification, APPROVED)

    def test_cannot_sell_more_than_stock(self):
        with self.assertRaises(SaleError):
            add_to_cart(open_cart(self.booth, self.seller), self.stand.pk, 11)

    def test_stock_rechecked_at_checkout(self):
        cart = open_cart(self.booth, self.seller)
        add_to_cart(cart, self.stand.pk, 5)
        Goods.objects.filter(pk=self.stand.pk).update(stock=2)  # sold elsewhere meanwhile
        with self.assertRaises(SaleError):
            checkout(cart, self.seller, CASH)
        self.assertFalse(Transaction.objects.exists())

    def test_empty_cart_cannot_checkout(self):
        with self.assertRaises(SaleError):
            checkout(open_cart(self.booth, self.seller), self.seller, CASH)

    def test_cart_checked_out_only_once(self):
        cart = open_cart(self.booth, self.seller)
        add_to_cart(cart, self.stand.pk, 1)
        checkout(cart, self.seller, CASH)
        with self.assertRaises(SaleError):
            checkout(cart, self.seller, CASH)


class VerifiedOnlyTests(POSFixture):
    def test_pending_goods_cannot_be_added(self):
        with self.assertRaises(SaleError):
            add_to_cart(open_cart(self.booth, self.seller), self.pending.pk, 1)

    def test_rejected_goods_cannot_be_added(self):
        rejected = self.make_goods("Bootleg", "10.00", 5, VerificationStatus.REJECTED)
        with self.assertRaises(SaleError):
            add_to_cart(open_cart(self.booth, self.seller), rejected.pk, 1)

    def test_goods_of_another_booth_cannot_be_added(self):
        other_booth = make_booth(make_seller("other"), name="Booth B", table=2, verification=APPROVED)
        foreign = self.make_goods("Foreign", "10.00", 5, APPROVED, booth=other_booth)
        with self.assertRaises(SaleError):
            add_to_cart(open_cart(self.booth, self.seller), foreign.pk, 1)

    def test_goods_unapproved_after_adding_blocks_checkout(self):
        cart = open_cart(self.booth, self.seller)
        add_to_cart(cart, self.stand.pk, 1)
        Goods.objects.filter(pk=self.stand.pk).update(verification=VerificationStatus.REJECTED)
        with self.assertRaises(SaleError):
            checkout(cart, self.seller, CASH)

    def test_pos_lists_only_approved_goods(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("sales:pos", args=[self.booth.pk]))
        self.assertContains(response, "Stand")
        self.assertNotContains(response, "Pending item")

    def test_unapproved_booth_cannot_open_pos(self):
        self.booth.verification = VerificationStatus.PENDING
        self.booth.save()
        self.client.force_login(self.user)
        response = self.client.get(reverse("sales:pos", args=[self.booth.pk]))
        self.assertRedirects(response, reverse("booths:my_booths"))


class POSViewTests(POSFixture):
    """The demo path through the real URLs, plus ownership checks on every POS view."""

    def test_add_checkout_void_through_views(self):
        self.client.force_login(self.user)
        pk = self.booth.pk
        self.client.post(reverse("sales:cart_add", args=[pk]), {"goods_id": self.stand.pk, "quantity": 2})
        response = self.client.post(reverse("sales:checkout", args=[pk]), {"payment_method": "cash"})
        tx = Transaction.objects.get()
        self.assertRedirects(response, reverse("sales:transaction_detail", args=[pk, tx.pk]))
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.stock, 8)
        self.client.post(reverse("sales:transaction_void", args=[pk, tx.pk]))
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.stock, 10)
        history = self.client.get(reverse("sales:transaction_list", args=[pk]))
        self.assertContains(history, tx.invoice_id)
        self.assertContains(history, "Voided")

    def test_void_requires_post(self):
        tx = self.sell(self.stand, 1)
        self.client.force_login(self.user)
        response = self.client.get(reverse("sales:transaction_void", args=[self.booth.pk, tx.pk]))
        self.assertEqual(response.status_code, 405)

    def test_other_seller_gets_403_on_every_pos_view(self):
        tx = self.sell(self.stand, 1)
        self.client.force_login(make_seller("intruder"))
        pk = self.booth.pk
        for method, url in [
            ("get", reverse("sales:pos", args=[pk])),
            ("post", reverse("sales:cart_add", args=[pk])),
            ("post", reverse("sales:checkout", args=[pk])),
            ("get", reverse("sales:transaction_list", args=[pk])),
            ("get", reverse("sales:transaction_detail", args=[pk, tx.pk])),
            ("post", reverse("sales:transaction_void", args=[pk, tx.pk])),
        ]:
            with self.subTest(url=url):
                self.assertEqual(getattr(self.client, method)(url).status_code, 403)
        tx.refresh_from_db()
        self.assertEqual(tx.status, Transaction.Status.COMPLETED)

    def test_transaction_of_another_booth_is_404(self):
        other_user = make_seller("other")
        other_booth = make_booth(other_user, name="Booth B", table=2, verification=APPROVED)
        tx = self.sell(self.stand, 1)
        self.client.force_login(other_user)
        url = reverse("sales:transaction_detail", args=[other_booth.pk, tx.pk])
        self.assertEqual(self.client.get(url).status_code, 404)


class ModelRulesTests(TestCase):
    """Model-level rules from the proposal that the POS views will rely on."""

    def setUp(self):
        user = User.objects.create_user("seller1", password="Str0ng!Pass")
        self.seller = Seller.objects.create(user=user, seller_name="Seller")
        self.bank = BankAccount.objects.create(
            bank_account_number="1234567890", bank_name="KBank", holder_name="Seller"
        )
        self.booth = Booth.objects.create(booth_name="Booth A", table_number=1, bank_account=self.bank)
        self.goods = Goods.objects.create(
            goods_name="Keychain", goods_price=Decimal("50.00"), stock=10,
            fandom=Fandom.objects.create(fandom="Fandom"),
            merch_type=MerchType.objects.create(name="Keychain"),
            verification=VerificationStatus.APPROVED,
        )

    def test_booth_name_is_unique(self):
        with self.assertRaises(IntegrityError):
            Booth.objects.create(booth_name="Booth A", table_number=2, bank_account=self.bank)

    def test_table_number_must_be_positive(self):
        booth = Booth(booth_name="Booth B", table_number=0, bank_account=self.bank)
        with self.assertRaises(ValidationError):
            booth.full_clean()

    def test_bank_account_is_masked(self):
        self.assertEqual(self.bank.masked_number, "******7890")
        self.assertNotIn("123456", str(self.bank))

    def test_renaming_approved_goods_resets_verification(self):
        self.goods.goods_name = "Something else"
        self.goods.save()
        self.goods.refresh_from_db()
        self.assertEqual(self.goods.verification, VerificationStatus.PENDING)

    def test_stock_change_keeps_verification(self):
        self.goods.stock = 5
        self.goods.save(update_fields=["stock"])
        self.goods.refresh_from_db()
        self.assertEqual(self.goods.verification, VerificationStatus.APPROVED)

    def test_transaction_gets_invoice_id_and_one_per_cart(self):
        cart = Cart.objects.create(booth=self.booth, created_by=self.seller)
        tx = Transaction.objects.create(
            cart=cart, booth=self.booth, created_by=self.seller,
            total_amount=Decimal("100.00"), payment_method=Transaction.PaymentMethod.CASH,
        )
        self.assertTrue(tx.invoice_id.startswith("INV-"))
        self.assertEqual(tx.status, Transaction.Status.COMPLETED)
        item = TransactionItem.objects.create(
            transaction=tx, goods=self.goods, goods_name="Keychain",
            unit_price=Decimal("50.00"), quantity=2,
        )
        self.assertEqual(item.line_total, Decimal("100.00"))
        with self.assertRaises(IntegrityError):
            Transaction.objects.create(
                cart=cart, booth=self.booth, created_by=self.seller,
                total_amount=Decimal("1.00"), payment_method=Transaction.PaymentMethod.CASH,
            )
