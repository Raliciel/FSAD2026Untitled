from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.tests import make_seller, make_staff
from booths.models import VerificationStatus
from booths.tests import make_booth
from sales.models import Transaction
from sales.services import add_to_cart, checkout, open_cart, void_transaction

from .models import Fandom, Goods, GoodsList, MerchType

APPROVED = VerificationStatus.APPROVED


class PublicCatalogTests(TestCase):
    def setUp(self):
        self.seller = make_seller("owner")
        self.booth_a = make_booth(self.seller, name="Starlight Prints", table=1, verification=APPROVED)
        self.booth_b = make_booth(make_seller("other"), name="Moonbeam Charms", table=2, verification=APPROVED)
        self.pending_booth = make_booth(make_seller("new"), name="Hidden Booth", table=3)
        self.genshin = Fandom.objects.create(fandom="Genshin Impact")
        self.jjk = Fandom.objects.create(fandom="Jujutsu Kaisen")
        self.stand = MerchType.objects.create(name="Acrylic stand")
        self.paimon = self.goods("Paimon stand", self.genshin, self.booth_a)
        self.gojo = self.goods("Gojo keychain", self.jjk, self.booth_b)
        self.unapproved = self.goods("Unreviewed print", self.genshin, self.booth_a, VerificationStatus.PENDING)
        self.in_pending_booth = self.goods("Secret item", self.genshin, self.pending_booth)

    def goods(self, name, fandom, booth, verification=APPROVED, stock=10):
        g = Goods.objects.create(
            goods_name=name, goods_price=Decimal("100.00"), stock=stock,
            fandom=fandom, merch_type=self.stand, verification=verification,
        )
        GoodsList.objects.create(booth=booth, goods=g)
        return g

    def search(self, **params):
        return self.client.get(reverse("catalog:goods_list"), params)

    def names(self, response):
        return [g.goods_name for g in response.context["page"]]

    def test_only_approved_goods_in_approved_booths_are_public(self):
        self.assertEqual(sorted(self.names(self.search())), ["Gojo keychain", "Paimon stand"])

    def test_filter_by_fandom(self):
        self.assertEqual(self.names(self.search(fandom=self.jjk.pk)), ["Gojo keychain"])

    def test_filter_by_booth(self):
        self.assertEqual(self.names(self.search(booth=self.booth_a.pk)), ["Paimon stand"])

    def test_pending_booth_not_offered_as_filter(self):
        response = self.search(booth=self.pending_booth.pk)
        self.assertFalse(response.context["form"].is_valid())
        self.assertNotContains(response, "Hidden Booth")

    def test_text_search_matches_booth_name(self):
        self.assertEqual(self.names(self.search(q="moonbeam")), ["Gojo keychain"])

    def test_text_search_does_not_leak_pending_booth(self):
        self.assertEqual(self.names(self.search(q="Hidden")), [])

    def test_detail_of_unapproved_goods_is_404(self):
        url = reverse("catalog:goods_detail", args=[self.unapproved.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_recommendations_rank_best_sellers_and_ignore_voided(self):
        seller = self.seller.seller
        cart = open_cart(self.booth_a, seller)
        add_to_cart(cart, self.paimon.pk, 1)
        checkout(cart, seller, Transaction.PaymentMethod.CASH)
        # A bigger sale of Gojo that was voided must not count.
        gojo_seller = self.booth_b.sellers.get()
        cart = open_cart(self.booth_b, gojo_seller)
        add_to_cart(cart, self.gojo.pk, 5)
        void_transaction(checkout(cart, gojo_seller, Transaction.PaymentMethod.CASH), gojo_seller)
        recommended = self.search().context["recommended"]
        self.assertEqual(recommended[0], self.paimon)
        self.assertNotIn(self.unapproved, recommended)
        self.assertNotIn(self.in_pending_booth, recommended)

    def test_recommendations_hidden_while_searching(self):
        self.assertEqual(self.search(q="gojo").context["recommended"], [])


class GoodsVerificationTests(TestCase):
    """Staff approval is what makes goods visible and sellable."""

    def setUp(self):
        self.booth = make_booth(make_seller("owner"), verification=APPROVED)
        self.goods = Goods.objects.create(
            goods_name="Badge", goods_price=Decimal("50.00"), stock=5,
            fandom=Fandom.objects.create(fandom="Blue Lock"),
            merch_type=MerchType.objects.create(name="Badge"),
        )
        GoodsList.objects.create(booth=self.booth, goods=self.goods)
        self.url = reverse("catalog:goods_review", args=[self.booth.pk, self.goods.pk])

    def test_staff_approves_goods(self):
        self.client.force_login(make_staff())
        self.client.post(self.url, {"review_result": "approved"})
        self.goods.refresh_from_db()
        self.assertEqual(self.goods.verification, APPROVED)
        self.assertTrue(self.goods.reviews.exists())

    def test_seller_cannot_approve_own_goods(self):
        self.client.force_login(self.booth.sellers.get().user)
        self.assertEqual(self.client.post(self.url, {"review_result": "approved"}).status_code, 403)
        self.goods.refresh_from_db()
        self.assertEqual(self.goods.verification, VerificationStatus.PENDING)
