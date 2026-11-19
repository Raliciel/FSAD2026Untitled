from django.contrib import admin

from .models import Fandom, Goods, GoodsList, GoodsReview, MerchType


class AddedByMixin:
    """Staff-managed lookup tables: record which staff member added each row."""

    def save_model(self, request, obj, form, change):
        if not change and hasattr(request.user, "staff"):
            obj.added_by = request.user.staff
        super().save_model(request, obj, form, change)


@admin.register(Fandom)
class FandomAdmin(AddedByMixin, admin.ModelAdmin):
    list_display = ("fandom", "added_by")
    exclude = ("added_by",)


@admin.register(MerchType)
class MerchTypeAdmin(AddedByMixin, admin.ModelAdmin):
    list_display = ("name", "added_by")
    exclude = ("added_by",)


@admin.register(Goods)
class GoodsAdmin(admin.ModelAdmin):
    list_display = ("goods_name", "goods_price", "stock", "verification")
    list_filter = ("verification", "fandom", "merch_type")
    search_fields = ("goods_name",)


admin.site.register(GoodsList)
admin.site.register(GoodsReview)
