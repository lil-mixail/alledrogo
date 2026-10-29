from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("product", "seller", "title", "unit_price", "quantity", "shipping_cost", "shipped_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("pk", "buyer", "status", "delivery_method", "created_at")
    list_filter = ("status", "delivery_method")
    search_fields = ("full_name", "phone", "city", "parcel_locker")
    inlines = [OrderItemInline]

