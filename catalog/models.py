from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from accounts.validators import IMAGE_VALIDATORS
from booths.models import REVIEW_RESULTS, VerificationStatus

MAX_GOODS_PRICE = 1_000_000
MAX_STOCK = 100_000


class Fandom(models.Model):
    fandom_id = models.BigAutoField(primary_key=True)
    fandom = models.CharField(max_length=100, unique=True)
    added_by = models.ForeignKey(
        "accounts.Staff", null=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self):
        return self.fandom


class MerchType(models.Model):
    type_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)  # "fandom" column in the ER diagram
    added_by = models.ForeignKey(
        "accounts.Staff", null=True, on_delete=models.SET_NULL, related_name="+"
    )

    def __str__(self):
        return self.name


class Goods(models.Model):
    goods_id = models.BigAutoField(primary_key=True)
    goods_name = models.CharField(max_length=150, db_index=True)  # searched by customers
    goods_image = models.ImageField(upload_to="goods/", blank=True, validators=IMAGE_VALIDATORS)
    goods_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(MAX_GOODS_PRICE)],
    )
    stock = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(MAX_STOCK)])
    verification = models.CharField(
        max_length=10, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )
    fandom = models.ForeignKey(Fandom, on_delete=models.PROTECT, related_name="goods")
    merch_type = models.ForeignKey(MerchType, on_delete=models.PROTECT, related_name="goods")
    booths = models.ManyToManyField("booths.Booth", through="GoodsList", related_name="goods")

    class Meta:
        verbose_name_plural = "goods"

    def __str__(self):
        return self.goods_name

    def save(self, *args, **kwargs):
        # 4.3.5: renaming or re-imaging approved goods sends them back for review,
        # so a banned item cannot replace an approved one.
        if self.pk and self.verification == VerificationStatus.APPROVED:
            old = Goods.objects.filter(pk=self.pk).values("goods_name", "goods_image").first()
            if old and (old["goods_name"], old["goods_image"]) != (self.goods_name, self.goods_image.name):
                self.verification = VerificationStatus.PENDING
                if kwargs.get("update_fields") is not None:
                    kwargs["update_fields"] = {*kwargs["update_fields"], "verification"}
        super().save(*args, **kwargs)


class GoodsList(models.Model):
    list_id = models.BigAutoField(primary_key=True)
    booth = models.ForeignKey(
        "booths.Booth", on_delete=models.CASCADE, related_name="goods_entries"
    )
    goods = models.ForeignKey(Goods, on_delete=models.CASCADE, related_name="goods_entries")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["booth", "goods"], name="unique_goods_per_booth")
        ]


class GoodsReview(models.Model):
    review_id = models.BigAutoField(primary_key=True)
    goods = models.ForeignKey(Goods, on_delete=models.CASCADE, related_name="reviews")
    staff = models.ForeignKey("accounts.Staff", on_delete=models.PROTECT)
    review_result = models.CharField(max_length=10, choices=REVIEW_RESULTS)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
