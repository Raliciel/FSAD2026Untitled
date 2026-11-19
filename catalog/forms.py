from django import forms

from booths.models import REVIEW_RESULTS, Booth, VerificationStatus

from .models import Fandom, Goods, GoodsReview, MerchType


class GoodsSearchForm(forms.Form):
    q = forms.CharField(
        required=False, max_length=100, label="Search",
        widget=forms.TextInput(attrs={"placeholder": "Goods, fandom, type or booth"}),
    )
    fandom = forms.ModelChoiceField(
        Fandom.objects.order_by("fandom"), required=False, empty_label="All fandoms"
    )
    merch_type = forms.ModelChoiceField(
        MerchType.objects.order_by("name"), required=False, empty_label="All types"
    )
    # FR-29: customers look for a specific booth; only booths they can actually visit.
    booth = forms.ModelChoiceField(
        Booth.objects.filter(verification=VerificationStatus.APPROVED, is_active=True).order_by("table_number"),
        required=False, empty_label="All booths",
    )


class GoodsForm(forms.ModelForm):
    class Meta:
        model = Goods
        fields = ("goods_name", "goods_image", "goods_price", "stock", "fandom", "merch_type")


class GoodsReviewForm(forms.ModelForm):
    review_result = forms.ChoiceField(choices=REVIEW_RESULTS)
    comment = forms.CharField(required=False, max_length=500)

    class Meta:
        model = GoodsReview
        fields = ("review_result", "comment")
