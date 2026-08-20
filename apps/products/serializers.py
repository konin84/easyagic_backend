from rest_framework import serializers

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "slug", "name",
            "kind", "kind_display", "category", "category_display",
            "description", "unit", "image",
        ]
        read_only_fields = fields

    def get_image(self, product):
        """One field for the app: uploaded file if there is one, else the URL, else null."""
        image = product.display_image
        if not image:
            return None
        request = self.context.get("request")
        if request is not None and image.startswith("/"):
            return request.build_absolute_uri(image)
        return image
