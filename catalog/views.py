from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import seller_required, staff_required
from booths.models import Booth, VerificationStatus
from booths.services import member_booth_or_403
from sales.models import Transaction, TransactionItem

from .forms import GoodsForm, GoodsReviewForm, GoodsSearchForm
from .models import Goods, GoodsList

APPROVED = VerificationStatus.APPROVED


PUBLIC_BOOTH = {"booth__verification": APPROVED, "booth__is_active": True}
RECOMMENDATION_COUNT = 4


def public_goods():
    """Goods a customer may see: approved goods listed by at least one approved, active booth."""
    listings = GoodsList.objects.filter(**PUBLIC_BOOTH).select_related("booth")
    return (
        Goods.objects.filter(
            verification=APPROVED,
            goods_entries__booth__verification=APPROVED, goods_entries__booth__is_active=True,
        )
        .distinct()
        .select_related("fandom", "merch_type")
        .prefetch_related(Prefetch("goods_entries", queryset=listings, to_attr="listings"))
    )


def recommended_goods(limit=RECOMMENDATION_COUNT):
    """Landing page picks: best sellers (completed sales), topped up with the newest goods."""
    best_ids = list(
        TransactionItem.objects.filter(transaction__status=Transaction.Status.COMPLETED)
        .values("goods_id").annotate(sold=Sum("quantity")).order_by("-sold", "goods_id")
        .values_list("goods_id", flat=True)[: limit * 3]
    )
    public = public_goods().filter(stock__gt=0)
    by_id = public.in_bulk(best_ids)
    picks = [by_id[pk] for pk in best_ids if pk in by_id][:limit]
    if len(picks) < limit:
        picks += list(public.exclude(pk__in=[g.pk for g in picks]).order_by("-goods_id")[: limit - len(picks)])
    return picks


# --- Customer (anonymous) -----------------------------------------------------
def goods_list(request):
    """Use cases: View Goods + Search Goods (by name, fandom, type or booth)."""
    form = GoodsSearchForm(request.GET or None)
    goods = public_goods().order_by("goods_name")
    searching = False
    if form.is_valid():
        data = form.cleaned_data
        searching = any(data.values())
        if data["q"]:
            q = data["q"]
            goods = goods.filter(
                Q(goods_name__icontains=q)
                | Q(fandom__fandom__icontains=q)
                | Q(merch_type__name__icontains=q)
                | Q(goods_entries__booth__booth_name__icontains=q, goods_entries__booth__verification=APPROVED)
            )
        if data["fandom"]:
            goods = goods.filter(fandom=data["fandom"])
        if data["merch_type"]:
            goods = goods.filter(merch_type=data["merch_type"])
        if data["booth"]:
            goods = goods.filter(goods_entries__booth=data["booth"])
    page = Paginator(goods, 20).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "catalog/goods_list.html", {
        "form": form, "page": page, "querystring": params.urlencode(), "searching": searching,
        "recommended": [] if searching else recommended_goods(),
    })


def goods_detail(request, pk):
    goods = get_object_or_404(public_goods(), pk=pk)
    return render(request, "catalog/goods_detail.html", {"goods": goods})


# --- Seller ---------------------------------------------------------------------
@seller_required
def submit_goods(request, booth_pk):
    """Use case: Submit goods list."""
    booth = member_booth_or_403(request, booth_pk)
    if booth.verification == VerificationStatus.REJECTED:
        raise PermissionDenied
    if request.method == "POST":
        form = GoodsForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                goods = form.save()
                GoodsList.objects.create(booth=booth, goods=goods)
            messages.success(request, "Goods submitted for verification.")
            return redirect("catalog:submit_goods", booth_pk=booth.pk)
    else:
        form = GoodsForm()
    entries = booth.goods_entries.select_related("goods", "goods__fandom", "goods__merch_type")
    return render(request, "catalog/submit_goods.html", {"booth": booth, "form": form, "entries": entries})


# --- Staff ----------------------------------------------------------------------
@staff_required
def booth_goods_review(request, booth_pk):
    """Use case: verify goods list."""
    booth = get_object_or_404(Booth, pk=booth_pk)
    entries = booth.goods_entries.select_related("goods", "goods__fandom", "goods__merch_type")
    return render(request, "catalog/booth_goods_review.html", {"booth": booth, "entries": entries})


@staff_required
@require_POST
def goods_review(request, booth_pk, goods_pk):
    entry = get_object_or_404(
        GoodsList.objects.select_related("goods"), booth_id=booth_pk, goods_id=goods_pk
    )
    form = GoodsReviewForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            review = form.save(commit=False)
            review.goods = entry.goods
            review.staff = request.user.staff
            review.save()
            entry.goods.verification = review.review_result
            entry.goods.save(update_fields=["verification"])
        messages.success(request, f"{entry.goods} {review.review_result}.")
    else:
        messages.error(request, "Invalid review.")
    return redirect("catalog:booth_goods_review", booth_pk=booth_pk)
