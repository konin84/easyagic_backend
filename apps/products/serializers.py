from rest_framework import serializers

from .models import Product
from .translation import localized, translated_labels


class ProductSerializer(serializers.ModelSerializer):
    """
    Serves the catalogue in the reader's language.

    `language` and `labels` come from the view via context so the translation
    lookup happens once per request, not once per product.
    """

    name = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()
    kind_display = serializers.SerializerMethodField()
    category_display = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    language = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "slug", "name",
            "kind", "kind_display", "category", "category_display",
            "description", "unit", "image", "image_credit", "language",
        ]
        read_only_fields = fields

    @property
    def _language(self):
        return self.context.get("language", "en")

    def _text(self, product):
        cached = self.context.setdefault("_localized", {})
        if product.pk not in cached:
            cached[product.pk] = localized(product, self._language)
        return cached[product.pk]

    def get_name(self, product):
        return self._text(product)["name"]

    def get_description(self, product):
        return self._text(product)["description"]

    def get_unit(self, product):
        return self._text(product)["unit"]

    def _label(self, english):
        return self.context.get("labels", {}).get(english, english)

    def get_kind_display(self, product):
        return self._label(product.get_kind_display())

    def get_category_display(self, product):
        return self._label(product.get_category_display())

    def get_language(self, product):
        """Which language this payload is actually in — English when unavailable."""
        language = self._language
        if language == "en":
            return "en"
        return language if self._text(product)["name"] != product.name else "en"

    def get_image(self, product):
        """One field for the app: uploaded file, else photo URL, else generated card."""
        image = product.display_image
        if not image:
            return None
        request = self.context.get("request")
        if request is not None and image.startswith("/"):
            return request.build_absolute_uri(image)
        return image
