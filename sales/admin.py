from django.contrib import admin

from .models import Cart, CartItem, Transaction, TransactionItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("cart_id", "booth", "status", "created_at")
    list_filter = ("status",)
    inlines = [CartItemInline]


class TransactionItemInline(admin.TabularInline):
    model = TransactionItem
    extra = 0


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("invoice_id", "booth", "total_amount", "payment_method", "status", "created_at")
    list_filter = ("status", "payment_method")
    search_fields = ("invoice_id",)
    inlines = [TransactionItemInline]
