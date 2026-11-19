import secrets

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Cart(models.Model):
    """UC03-02: a cart belongs to one booth and is checked out at most once."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CHECKED_OUT = "checked_out", "Checked out"
        CANCELLED = "cancelled", "Cancelled"

    cart_id = models.BigAutoField(primary_key=True)
    booth = models.ForeignKey("booths.Booth", on_delete=models.PROTECT, related_name="carts")
    created_by = models.ForeignKey("accounts.Seller", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)


class CartItem(models.Model):
    """The ER diagram puts goods_id/quantity on Cart; normalised here so a cart can hold many goods."""

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    goods = models.ForeignKey("catalog.Goods", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cart", "goods"], name="unique_goods_per_cart")
        ]

    @property
    def line_total(self):
        return self.goods.goods_price * self.quantity


def new_invoice_id():
    return f"INV-{timezone.now():%Y%m%d}-{secrets.token_hex(4).upper()}"


class Transaction(models.Model):
    """FR-18..21: created once per cart; voiding keeps the record (UC03-04)."""

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        ONLINE = "online", "Online (QR)"

    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        VOIDED = "voided", "Voided"
        CANCELLED = "cancelled", "Cancelled"

    transaction_id = models.BigAutoField(primary_key=True)
    invoice_id = models.CharField(max_length=30, unique=True, default=new_invoice_id, editable=False)
    # Always computed on the server from TransactionItem rows, never taken from the browser.
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    cart = models.OneToOneField(Cart, on_delete=models.PROTECT, related_name="transaction")
    booth = models.ForeignKey("booths.Booth", on_delete=models.PROTECT, related_name="transactions")
    created_by = models.ForeignKey("accounts.Seller", on_delete=models.PROTECT, related_name="+")
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.COMPLETED)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    voided_by = models.ForeignKey(
        "accounts.Seller", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    voided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.invoice_id


class TransactionItem(models.Model):
    """FR-19 goods list. Name and price are copied so later edits don't rewrite history."""

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="items")
    goods = models.ForeignKey("catalog.Goods", on_delete=models.PROTECT, related_name="+")
    goods_name = models.CharField(max_length=150)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["transaction", "goods"], name="unique_goods_per_transaction")
        ]

    @property
    def line_total(self):
        return self.unit_price * self.quantity
