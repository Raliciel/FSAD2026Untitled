from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import AuditLog, Seller, Staff, User


class SellerInline(admin.StackedInline):
    model = Seller
    extra = 0
    max_num = 1


class StaffInline(admin.StackedInline):
    model = Staff
    extra = 0
    max_num = 1


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (("Convention role", {"fields": ("role",)}),)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + ((None, {"fields": ("role",)}),)
    list_display = ("username", "email", "role", "is_active")
    list_filter = ("role", "is_active")
    inlines = [SellerInline, StaffInline]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only: an audit trail that can be edited is not an audit trail."""

    list_display = ("created_at", "action", "username", "target", "ip_address")
    list_filter = ("action",)
    search_fields = ("username", "target")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
