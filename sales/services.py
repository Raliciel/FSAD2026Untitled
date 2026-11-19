"""POS rules (UC03-02..04). Views and seed_demo both go through these functions."""
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from booths.models import VerificationStatus
from catalog.models import Goods

from .models import Cart, CartItem, Transaction, TransactionItem

APPROVED = VerificationStatus.APPROVED


class SaleError(Exception):
    """A business rule stopped the sale; the message is safe to show the seller."""


def booth_can_sell(booth):
    return booth.is_active and booth.verification == APPROVED


def sellable_goods(booth):
    """Only staff-approved goods listed by this booth can be sold."""
    return Goods.objects.filter(goods_entries__booth=booth, verification=APPROVED)


def open_cart(booth, seller):
    cart = Cart.objects.filter(booth=booth, created_by=seller, status=Cart.Status.OPEN).first()
    return cart or Cart.objects.create(booth=booth, created_by=seller)


def add_to_cart(cart, goods_id, quantity=1):
    if quantity < 1:
        raise SaleError("Quantity must be at least 1.")
    goods = sellable_goods(cart.booth).filter(pk=goods_id).first()
    if goods is None:
        raise SaleError("That item is not approved for sale at this booth.")
    item = CartItem.objects.filter(cart=cart, goods=goods).first() or CartItem(cart=cart, goods=goods, quantity=0)
    if item.quantity + quantity > goods.stock:
        raise SaleError(f"Only {goods.stock} of {goods} left in stock.")
    item.quantity += quantity
    item.save()
    return item


def cart_total(cart):
    return sum(
        (i.goods.goods_price * i.quantity for i in cart.items.select_related("goods")), Decimal("0")
    )


@transaction.atomic
def checkout(cart, seller, payment_method):
    """FR-18..21: one transaction per cart; stock is locked, checked and reduced together."""
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    if cart.status != Cart.Status.OPEN:
        raise SaleError("This cart was already checked out.")
    if payment_method not in Transaction.PaymentMethod.values:
        raise SaleError("Choose a payment method.")
    items = list(cart.items.all())
    if not items:
        raise SaleError("The cart is empty.")
    # Lock the goods rows so two checkouts cannot sell the same last item.
    goods_by_id = Goods.objects.select_for_update().in_bulk([i.goods_id for i in items])
    sellable_ids = set(sellable_goods(cart.booth).values_list("pk", flat=True))
    for item in items:
        goods = goods_by_id[item.goods_id]
        if goods.pk not in sellable_ids:
            raise SaleError(f"{goods} is no longer approved for sale.")
        if goods.stock < item.quantity:
            raise SaleError(f"Only {goods.stock} of {goods} left in stock.")
    total = sum((goods_by_id[i.goods_id].goods_price * i.quantity for i in items), Decimal("0"))
    tx = Transaction.objects.create(
        cart=cart, booth=cart.booth, created_by=seller,
        total_amount=total, payment_method=payment_method,
    )
    for item in items:
        goods = goods_by_id[item.goods_id]
        TransactionItem.objects.create(
            transaction=tx, goods=goods, goods_name=goods.goods_name,
            unit_price=goods.goods_price, quantity=item.quantity,
        )
        # update() with F() skips Goods.save(), so a stock change never resets verification.
        Goods.objects.filter(pk=goods.pk).update(stock=F("stock") - item.quantity)
    cart.status = Cart.Status.CHECKED_OUT
    cart.save(update_fields=["status"])
    return tx


@transaction.atomic
def void_transaction(tx, seller):
    """UC03-04: keep the record, mark it voided and put the stock back. Only once."""
    tx = Transaction.objects.select_for_update().get(pk=tx.pk)
    if tx.status != Transaction.Status.COMPLETED:
        raise SaleError(f"{tx} is already {tx.get_status_display().lower()}.")
    for item in tx.items.all():
        Goods.objects.filter(pk=item.goods_id).update(stock=F("stock") + item.quantity)
    tx.status = Transaction.Status.VOIDED
    tx.voided_by = seller
    tx.voided_at = timezone.now()
    tx.save(update_fields=["status", "voided_by", "voided_at"])
    return tx
