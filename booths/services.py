from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404

from accounts.security import Action, audit

from .models import Blacklist, Booth


def blacklist_hits(sellers, bank_account_number=""):
    """Use case: check blacklist (included by Register Booth)."""
    query = Q(seller__in=list(sellers))
    if bank_account_number:
        query |= Q(bank_account_number=bank_account_number)
    return Blacklist.objects.filter(query)


def member_booth_or_403(request, pk):
    """A booth the logged-in seller belongs to; anyone else gets 403 and an audit entry."""
    booth = get_object_or_404(Booth, pk=pk)
    if not booth.sellers.filter(pk=request.user.seller.pk).exists():
        audit(Action.ACCESS_DENIED, request, target=request.path)
        raise PermissionDenied
    return booth
