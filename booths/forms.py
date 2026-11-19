from django import forms
from django.db import transaction

from accounts.models import Seller

from .models import REVIEW_RESULTS, BankAccount, Booth, BoothReview, SellerBooth
from .services import blacklist_hits


class BoothRegistrationForm(forms.ModelForm):
    account_number = forms.CharField(max_length=30, label="Bank account number")
    bank_name = forms.CharField(max_length=100)
    holder_name = forms.CharField(max_length=100, label="Account holder name")
    partner_username = forms.CharField(
        required=False, label="Co-seller's username (optional)",
        help_text="Your booth partner must already have a seller account.",
    )

    class Meta:
        model = Booth
        fields = ("booth_name", "booth_profile_picture", "table_number")

    def __init__(self, *args, seller, **kwargs):
        super().__init__(*args, **kwargs)
        self.seller = seller

    def clean_partner_username(self):
        username = self.cleaned_data.get("partner_username", "").strip()
        if not username:
            return None
        try:
            partner = Seller.objects.get(user__username=username)
        except Seller.DoesNotExist:
            raise forms.ValidationError("No seller with that username.")
        if partner == self.seller:
            raise forms.ValidationError("You are already part of this booth.")
        return partner

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        sellers = [self.seller]
        if cleaned.get("partner_username"):
            sellers.append(cleaned["partner_username"])
        if blacklist_hits(sellers, cleaned.get("account_number", "")).exists():
            raise forms.ValidationError(
                "This registration cannot be accepted. Please contact the staff."
            )
        return cleaned

    @transaction.atomic
    def save(self):
        data = self.cleaned_data
        bank, _ = BankAccount.objects.get_or_create(
            bank_account_number=data["account_number"],
            defaults={"bank_name": data["bank_name"], "holder_name": data["holder_name"]},
        )
        booth = super().save(commit=False)
        booth.bank_account = bank
        booth.save()
        SellerBooth.objects.create(booth=booth, seller=self.seller)
        if data.get("partner_username"):
            SellerBooth.objects.create(booth=booth, seller=data["partner_username"])
        return booth


class BoothEditForm(forms.ModelForm):
    class Meta:
        model = Booth
        fields = ("booth_name", "booth_profile_picture", "table_number")


class BoothReviewForm(forms.ModelForm):
    review_result = forms.ChoiceField(choices=REVIEW_RESULTS)

    class Meta:
        model = BoothReview
        fields = ("review_result", "comment")
