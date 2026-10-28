from django.contrib import admin

from .models import Comment, Conversation, Message, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "seller", "price", "stock", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title", "seller__username")
    inlines = [ProductImageInline]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("product", "author", "rating", "created_at")
    search_fields = ("body", "author__username", "product__title")


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("sender", "body", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("product", "buyer", "seller", "updated_at")
    inlines = [MessageInline]

