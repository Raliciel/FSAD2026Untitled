"""Fake demo data so you can try BoothPOS right after cloning. LOCAL USE ONLY.

What it creates: 1 staff user, 2 sellers, 3 booths (one pending), 13 goods, 6 sales
(one voided) and one blacklisted bank account. Every name, bank account and sale is
made up. Safe to run repeatedly: existing rows are reused, never duplicated.

Quick start (after `pip install -r requirements.txt` and `python manage.py migrate`):

  1. Choose a password for the demo accounts. It must pass the project's password
     rules: 8+ characters, upper and lower case, and one of !@#$%^&*()_+
     Either fill in DEMO_PASSWORD below (do NOT commit it), or better, leave it
     empty and put this line in your .env (which git ignores):

         DEMO_PASSWORD=<your password>

     or pass it once on the command line:

         python manage.py seed_demo --password "<your password>"

  2. Run it:

         python manage.py seed_demo           # staff user can use the staff pages only
         python manage.py seed_demo --admin   # staff user can also open /admin/

  3. Log in at http://127.0.0.1:8000/accounts/login/ as staff.nok, mint.seller or
     ploy.seller with the password you chose.

Reset to a clean demo:  python manage.py flush  then  python manage.py seed_demo

It refuses to run when DJANGO_DEBUG is false, so it can't seed a real deployment
by accident (use --force only if you really mean it, e.g. a throwaway test server).
"""
import os
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Seller, Staff, User
from booths.models import BankAccount, Blacklist, Booth, BoothReview, SellerBooth, VerificationStatus
from catalog.models import Fandom, Goods, GoodsList, GoodsReview, MerchType
from sales.models import Transaction
from sales.services import add_to_cart, checkout, open_cart, void_transaction

# Password for ALL seeded accounts. Intentionally empty: see step 1 in the docstring.
# Order of precedence: --password option, DEMO_PASSWORD env var / .env, this value.
DEMO_PASSWORD = ""
APPROVED, PENDING = VerificationStatus.APPROVED, VerificationStatus.PENDING

STAFF = ("staff.nok", "Nok (Convention staff)")
SELLERS = [("mint.seller", "Mint"), ("ploy.seller", "Ploy")]

FANDOMS = ["Genshin Impact", "Honkai: Star Rail", "Jujutsu Kaisen", "Spy x Family", "Frieren", "Blue Lock"]
MERCH_TYPES = ["Acrylic stand", "Keychain", "Art print", "Sticker sheet", "Badge", "Postcard set"]

# booth name, table, owner username, bank (number, bank, holder), status, goods
# goods: name, fandom, type, price, stock, status
BOOTHS = [
    ("Starlight Prints", 12, "mint.seller", ("1234567012", "KBank", "Mint S."), APPROVED, [
        ("Paimon Emergency Food Acrylic Stand", "Genshin Impact", "Acrylic stand", "350.00", 15, APPROVED),
        ("Furina Art Print A4", "Genshin Impact", "Art print", "250.00", 20, APPROVED),
        ("Raiden Shogun Keychain", "Genshin Impact", "Keychain", "180.00", 25, APPROVED),
        ("Firefly Sticker Sheet", "Honkai: Star Rail", "Sticker sheet", "90.00", 40, APPROVED),
        ("Kafka Postcard Set", "Honkai: Star Rail", "Postcard set", "150.00", 12, APPROVED),
    ]),
    ("Moonbeam Charms", 7, "ploy.seller", ("9876543007", "SCB", "Ploy T."), APPROVED, [
        ("Gojo Satoru Acrylic Keychain", "Jujutsu Kaisen", "Keychain", "190.00", 30, APPROVED),
        ("Sukuna Postcard Set", "Jujutsu Kaisen", "Postcard set", "140.00", 3, APPROVED),
        ("Anya Peanut Badge", "Spy x Family", "Badge", "60.00", 50, APPROVED),
        ("Loid & Yor Art Print", "Spy x Family", "Art print", "220.00", 10, APPROVED),
        ("Frieren Mimic Sticker Sheet", "Frieren", "Sticker sheet", "85.00", 35, APPROVED),
        ("Fern & Stark Acrylic Stand", "Frieren", "Acrylic stand", "320.00", 8, APPROVED),
    ]),
    # Waiting for staff, so verification can be shown on seeded data too.
    ("Egoist Goods", 21, "ploy.seller", ("5550001021", "Bangkok Bank", "Ploy T."), PENDING, [
        ("Isagi Yoichi Badge", "Blue Lock", "Badge", "70.00", 20, PENDING),
        ("Bachira Meguru Acrylic Stand", "Blue Lock", "Acrylic stand", "300.00", 10, PENDING),
    ]),
]

# booth name -> list of (cart lines, payment, void?)
SALES = {
    "Starlight Prints": [
        ([("Paimon Emergency Food Acrylic Stand", 2), ("Firefly Sticker Sheet", 3)], "cash", False),
        ([("Furina Art Print A4", 1)], "online", False),
        ([("Paimon Emergency Food Acrylic Stand", 1), ("Kafka Postcard Set", 2)], "online", False),
        ([("Raiden Shogun Keychain", 4)], "cash", True),
    ],
    "Moonbeam Charms": [
        ([("Gojo Satoru Acrylic Keychain", 3), ("Anya Peanut Badge", 2)], "cash", False),
        ([("Fern & Stark Acrylic Stand", 1)], "online", False),
    ],
}

BLACKLISTED_ACCOUNT = "9999999999"


class Command(BaseCommand):
    help = "Create fake demo staff, sellers, booths, goods and sales for local testing (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Password for all seeded accounts (else DEMO_PASSWORD).")
        parser.add_argument("--admin", action="store_true",
                            help="Also let the demo staff user open the Django admin (superuser).")
        parser.add_argument("--force", action="store_true", help="Run even when DEBUG is false.")

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "seed_demo is for local development and DJANGO_DEBUG is false. "
                "Set DJANGO_DEBUG=true in .env, or pass --force on a throwaway server."
            )
        self.password = options["password"] or os.environ.get("DEMO_PASSWORD") or DEMO_PASSWORD
        if not self.password:
            raise CommandError(
                "No demo password set. Add DEMO_PASSWORD=<password> to .env or run "
                'python manage.py seed_demo --password "<password>" (see the top of seed_demo.py).'
            )
        try:
            validate_password(self.password)
        except ValidationError as e:
            raise CommandError("Demo password rejected: " + " ".join(e.messages))
        self.admin = options["admin"]
        self.seed()

    @transaction.atomic
    def seed(self):
        staff = self.user(STAFF[0], STAFF[1], User.Role.STAFF).staff
        sellers = {u: self.user(u, name, User.Role.SELLER).seller for u, name in SELLERS}
        fandoms = {n: Fandom.objects.get_or_create(fandom=n, defaults={"added_by": staff})[0] for n in FANDOMS}
        types = {n: MerchType.objects.get_or_create(name=n, defaults={"added_by": staff})[0] for n in MERCH_TYPES}

        Blacklist.objects.get_or_create(
            bank_account_number=BLACKLISTED_ACCOUNT,
            defaults={"reason": "Chargebacks at a previous event (demo entry)", "added_by": staff},
        )

        booths = {}
        for name, table, owner, (acct, bank, holder), status, goods in BOOTHS:
            bank_account, _ = BankAccount.objects.get_or_create(
                bank_account_number=acct, defaults={"bank_name": bank, "holder_name": holder}
            )
            booth, created = Booth.objects.get_or_create(
                booth_name=name,
                defaults={"table_number": table, "bank_account": bank_account, "verification": status},
            )
            SellerBooth.objects.get_or_create(booth=booth, seller=sellers[owner])
            if created and status == APPROVED:
                BoothReview.objects.create(booth=booth, staff=staff, review_result=APPROVED,
                                           comment="Documents and blacklist check OK.")
            for g_name, fandom, mtype, price, stock, g_status in goods:
                self.goods(booth, staff, g_name, fandoms[fandom], types[mtype], price, stock, g_status)
            booths[name] = booth

        for booth_name, sales in SALES.items():
            booth = booths[booth_name]
            if booth.transactions.exists():
                continue  # already seeded (or real sales were made); never duplicate
            seller = booth.sellers.first()
            for lines, payment, void in sales:
                cart = open_cart(booth, seller)
                for g_name, qty in lines:
                    add_to_cart(cart, booth.goods.get(goods_name=g_name).pk, qty)
                tx = checkout(cart, seller, payment)
                if void:
                    void_transaction(tx, seller)

        self.report(booths)

    def user(self, username, display_name, role):
        user, _ = User.objects.get_or_create(username=username, defaults={"role": role})
        user.role = role
        user.is_active = True
        if role == User.Role.STAFF and self.admin:
            user.is_staff = user.is_superuser = True  # only with --admin
        user.set_password(self.password)  # reset every run so the chosen password always works
        user.save()
        if role == User.Role.STAFF:
            Staff.objects.get_or_create(user=user, defaults={"staff_name": display_name})
        else:
            Seller.objects.get_or_create(user=user, defaults={"seller_name": display_name})
        return user

    def goods(self, booth, staff, name, fandom, merch_type, price, stock, status):
        entry = GoodsList.objects.filter(booth=booth, goods__goods_name=name).select_related("goods").first()
        if entry:
            return entry.goods  # keep current stock/status so earlier demo sales stay consistent
        goods = Goods.objects.create(
            goods_name=name, fandom=fandom, merch_type=merch_type,
            goods_price=Decimal(price), stock=stock, verification=status,
        )
        GoodsList.objects.create(booth=booth, goods=goods)
        if status == APPROVED:
            GoodsReview.objects.create(goods=goods, staff=staff, review_result=APPROVED)
        return goods

    def report(self, booths):
        w = self.stdout.write
        w(self.style.SUCCESS("\nDemo data ready."))
        w("All accounts use the demo password you set (it is not printed).")
        w(f"\n{'Role':<8} {'Username':<14} Booths")
        admin = User.objects.get(username=STAFF[0]).is_superuser
        w(f"{'staff':<8} {STAFF[0]:<14} (reviews booths and goods"
          + ("; can open /admin/)" if admin else "; run with --admin to open /admin/)"))
        for username, _ in SELLERS:
            owned = [f"{b.booth_name} (#{b.pk}, {b.get_verification_display().lower()})"
                     for b in booths.values() if b.sellers.filter(user__username=username).exists()]
            w(f"{'seller':<8} {username:<14} {', '.join(owned)}")
        done = Transaction.objects.filter(status=Transaction.Status.COMPLETED).count()
        voided = Transaction.objects.filter(status=Transaction.Status.VOIDED).count()
        w(f"\nGoods on sale: {Goods.objects.filter(verification=APPROVED).count()}  "
          f"Transactions: {done} completed, {voided} voided")
        w(f"Blacklisted bank account for the blacklist demo: {BLACKLISTED_ACCOUNT}")
        w("Free table numbers for a live booth: anything except "
          + ", ".join(str(n) for n in Booth.objects.order_by("table_number").values_list("table_number", flat=True)))
