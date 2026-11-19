from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from accounts.validators import IMAGE_VALIDATORS


class VerificationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


REVIEW_RESULTS = [
    (VerificationStatus.APPROVED.value, "Approve"),
    (VerificationStatus.REJECTED.value, "Reject"),
]


class BankAccount(models.Model):
    # The ER diagram's Bank_account carries staff_* columns, which look like a copy/paste slip;
    # here it stores the account holder instead.
    bank_account_number = models.CharField(max_length=30, primary_key=True)
    bank_name = models.CharField(max_length=100)
    holder_name = models.CharField(max_length=100)

    @property
    def masked_number(self):
        """Proposal 4.3.6: show only the last digits on screens and in logs."""
        return "*" * max(len(self.bank_account_number) - 4, 0) + self.bank_account_number[-4:]

    def __str__(self):
        return f"{self.bank_name} {self.masked_number}"


class Booth(models.Model):
    booth_id = models.BigAutoField(primary_key=True)
    booth_name = models.CharField(max_length=100, unique=True)  # UC02-01 ext. 5a
    booth_profile_picture = models.ImageField(
        upload_to="booths/", blank=True, validators=IMAGE_VALIDATORS
    )
    table_number = models.PositiveIntegerField(unique=True, validators=[MinValueValidator(1)])
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name="booths"
    )
    verification = models.CharField(
        max_length=10, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )
    sellers = models.ManyToManyField(
        "accounts.Seller", through="SellerBooth", related_name="booths"
    )
    # FR-11: staff deactivate booths instead of deleting them, so history is kept.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.booth_name} (table {self.table_number})"


class SellerBooth(models.Model):
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE)
    seller = models.ForeignKey("accounts.Seller", on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["booth", "seller"], name="unique_seller_per_booth")
        ]


class BoothReview(models.Model):
    review_id = models.BigAutoField(primary_key=True)
    booth = models.ForeignKey(Booth, on_delete=models.CASCADE, related_name="reviews")
    staff = models.ForeignKey("accounts.Staff", on_delete=models.PROTECT)
    review_result = models.CharField(max_length=10, choices=REVIEW_RESULTS)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Blacklist(models.Model):
    """Not in the ER diagram, but required by the 'check blacklist' use case."""

    seller = models.ForeignKey(
        "accounts.Seller", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    bank_account_number = models.CharField(max_length=30, blank=True)
    reason = models.TextField()
    added_by = models.ForeignKey(
        "accounts.Staff", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if not self.seller and not self.bank_account_number:
            raise ValidationError("Provide a seller, a bank account number, or both.")

    def __str__(self):
        return f"Blacklist: {self.seller or self.bank_account_number}"
