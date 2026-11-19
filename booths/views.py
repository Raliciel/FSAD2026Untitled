from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import seller_required, staff_required

from .forms import BoothEditForm, BoothRegistrationForm, BoothReviewForm
from .models import Booth, VerificationStatus
from .services import blacklist_hits, member_booth_or_403


@seller_required
def my_booths(request):
    booths = request.user.seller.booths.order_by("booth_name")
    return render(request, "booths/my_booths.html", {"booths": booths})


@seller_required
def booth_register(request):
    """Use case: Register Booth (includes check blacklist; continues to submit goods list)."""
    if request.method == "POST":
        form = BoothRegistrationForm(request.POST, request.FILES, seller=request.user.seller)
        if form.is_valid():
            booth = form.save()
            messages.success(request, "Booth registered. Submit your goods list for verification.")
            return redirect("catalog:submit_goods", booth_pk=booth.pk)
    else:
        form = BoothRegistrationForm(seller=request.user.seller)
    return render(request, "form.html", {"title": "Register a booth", "form": form, "submit": "Register booth"})


@seller_required
def booth_edit(request, pk):
    """Use case: Edit Booth's information (members only; edits require re-verification)."""
    booth = member_booth_or_403(request, pk)
    if request.method == "POST":
        form = BoothEditForm(request.POST, request.FILES, instance=booth)
        if form.is_valid():
            booth = form.save(commit=False)
            if form.has_changed():
                booth.verification = VerificationStatus.PENDING
            booth.save()
            messages.success(request, "Booth updated. Staff will re-verify any changes.")
            return redirect("booths:my_booths")
    else:
        form = BoothEditForm(instance=booth)
    return render(request, "form.html", {"title": f"Edit booth: {booth.booth_name}", "form": form, "submit": "Save"})


@staff_required
def review_list(request):
    status = request.GET.get("status", VerificationStatus.PENDING)
    if status not in VerificationStatus.values:
        status = VerificationStatus.PENDING
    booths = Booth.objects.filter(verification=status).order_by("created_at")
    return render(request, "booths/review_list.html", {"booths": booths, "status": status})


@staff_required
def booth_review(request, pk):
    """Use case: staff verifies a booth (and sees any blacklist hits)."""
    booth = get_object_or_404(Booth.objects.select_related("bank_account"), pk=pk)
    sellers = booth.sellers.select_related("user")
    hits = blacklist_hits(sellers, booth.bank_account_id)
    if request.method == "POST":
        form = BoothReviewForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                review = form.save(commit=False)
                review.booth = booth
                review.staff = request.user.staff
                review.save()
                booth.verification = review.review_result
                booth.save(update_fields=["verification"])
            messages.success(request, f"Booth {review.review_result}.")
            if review.review_result == VerificationStatus.APPROVED:
                # Next step of the same use case: verify this booth's goods list.
                return redirect("catalog:booth_goods_review", booth_pk=booth.pk)
            return redirect("booths:review_list")
    else:
        form = BoothReviewForm()
    return render(
        request, "booths/review.html",
        {"booth": booth, "sellers": sellers, "hits": hits, "form": form},
    )
