from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import seller_required
from booths.services import member_booth_or_403

from .models import CartItem, Transaction
from .services import (
    SaleError, add_to_cart, booth_can_sell, cart_total, checkout, open_cart, sellable_goods,
    void_transaction,
)


def selling_booth(request, booth_pk):
    """Member check (403), then the booth must be approved and active to sell."""
    booth = member_booth_or_403(request, booth_pk)
    if not booth_can_sell(booth):
        messages.error(request, "This booth must be approved by staff before it can sell.")
        return booth, redirect("booths:my_booths")
    return booth, None


@seller_required
def pos(request, booth_pk):
    """UC03-02: point of sale screen (goods to sell, current cart, checkout)."""
    booth, denied = selling_booth(request, booth_pk)
    if denied:
        return denied
    cart = open_cart(booth, request.user.seller)
    items = cart.items.select_related("goods").order_by("goods__goods_name")
    goods = sellable_goods(booth).select_related("fandom", "merch_type").order_by("goods_name")
    return render(request, "sales/pos.html", {
        "booth": booth, "cart": cart, "items": items, "goods": goods,
        "total": cart_total(cart), "payment_methods": Transaction.PaymentMethod.choices,
    })


@seller_required
@require_POST
def cart_add(request, booth_pk):
    booth, denied = selling_booth(request, booth_pk)
    if denied:
        return denied
    try:
        quantity = int(request.POST.get("quantity", 1))
        goods_id = int(request.POST.get("goods_id", 0))
        item = add_to_cart(open_cart(booth, request.user.seller), goods_id, quantity)
        messages.success(request, f"Added {quantity} x {item.goods}.")
    except ValueError:
        messages.error(request, "Invalid quantity.")
    except SaleError as e:
        messages.error(request, str(e))
    return redirect("sales:pos", booth_pk=booth.pk)


@seller_required
@require_POST
def cart_remove(request, booth_pk, goods_pk):
    booth, denied = selling_booth(request, booth_pk)
    if denied:
        return denied
    CartItem.objects.filter(cart=open_cart(booth, request.user.seller), goods_id=goods_pk).delete()
    return redirect("sales:pos", booth_pk=booth.pk)


@seller_required
@require_POST
def cart_checkout(request, booth_pk):
    booth, denied = selling_booth(request, booth_pk)
    if denied:
        return denied
    try:
        tx = checkout(
            open_cart(booth, request.user.seller), request.user.seller,
            request.POST.get("payment_method", ""),
        )
    except SaleError as e:
        messages.error(request, str(e))
        return redirect("sales:pos", booth_pk=booth.pk)
    messages.success(request, f"Payment recorded: {tx.invoice_id}, total {tx.total_amount} THB.")
    return redirect("sales:transaction_detail", booth_pk=booth.pk, pk=tx.pk)


@seller_required
def transaction_list(request, booth_pk):
    """FR-20: transaction history for one booth."""
    booth = member_booth_or_403(request, booth_pk)
    transactions = booth.transactions.select_related("created_by").prefetch_related("items")
    completed = transactions.filter(status=Transaction.Status.COMPLETED)
    return render(request, "sales/transaction_list.html", {
        "booth": booth, "transactions": transactions,
        "revenue": completed.aggregate(s=Sum("total_amount"))["s"] or 0,
        "completed_count": completed.count(),
    })


@seller_required
def transaction_detail(request, booth_pk, pk):
    booth = member_booth_or_403(request, booth_pk)
    tx = get_object_or_404(booth.transactions.select_related("created_by", "voided_by"), pk=pk)
    return render(request, "sales/transaction_detail.html", {"booth": booth, "tx": tx, "items": tx.items.all()})


@seller_required
@require_POST
def transaction_void(request, booth_pk, pk):
    booth = member_booth_or_403(request, booth_pk)
    tx = get_object_or_404(booth.transactions, pk=pk)
    try:
        void_transaction(tx, request.user.seller)
        messages.success(request, f"{tx.invoice_id} voided. Stock has been restored.")
    except SaleError as e:
        messages.error(request, str(e))
    return redirect("sales:transaction_detail", booth_pk=booth.pk, pk=tx.pk)
