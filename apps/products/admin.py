from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "category", "unit", "has_image", "is_active")
    list_filter = ("kind", "category", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(boolean=True, description="Image")
    def has_image(self, obj):
        return bool(obj.display_image)
