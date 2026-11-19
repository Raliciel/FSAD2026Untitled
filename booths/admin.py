from django.contrib import admin

from .models import BankAccount, Blacklist, Booth, BoothReview, SellerBooth


class SellerBoothInline(admin.TabularInline):
    model = SellerBooth
    extra = 0


@admin.register(Booth)
class BoothAdmin(admin.ModelAdmin):
    list_display = ("booth_name", "table_number", "verification", "is_active")
    list_filter = ("verification", "is_active")
    search_fields = ("booth_name", "table_number")
    inlines = [SellerBoothInline]


@admin.register(Blacklist)
class BlacklistAdmin(admin.ModelAdmin):
    list_display = ("__str__", "reason", "created_at")


admin.site.register(BankAccount)
admin.site.register(BoothReview)
