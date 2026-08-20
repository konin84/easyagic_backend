from django.db import models

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Product
from .serializers import ProductSerializer
from .translation import ensure_translations, translated_labels


def _context(request, products):
    """Translate once per request, then hand the results to the serializer."""
    language = getattr(request.user, "language", "en") or "en"
    ensure_translations(products, language)
    return {"request": request, "language": language, "labels": translated_labels(language)}


class ProductListView(APIView):
    """
    GET /api/products/ — the catalogue the app lists.

    Filters: ?kind=input|produce, ?category=<slug>, ?search=<name or description>
    Paging:  ?limit= (default 50, max 200), ?offset=
    """

    permission_classes = [IsAuthenticated]

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 200

    def get(self, request):
        products = Product.objects.filter(is_active=True)

        kind = request.query_params.get("kind")
        if kind:
            products = products.filter(kind=kind)

        category = request.query_params.get("category")
        if category:
            products = products.filter(category=category)

        search = request.query_params.get("search")
        if search:
            products = products.filter(
                models.Q(name__icontains=search) | models.Q(description__icontains=search)
            )

        try:
            limit = min(int(request.query_params.get("limit", self.DEFAULT_LIMIT)), self.MAX_LIMIT)
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except ValueError:
            return Response(
                {"error": "limit and offset must be whole numbers."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        limit = max(limit, 1)

        total = products.count()
        page = list(products[offset:offset + limit])

        return Response({
            "count": total,
            "limit": limit,
            "offset": offset,
            "results": ProductSerializer(page, many=True, context=_context(request, page)).data,
        })


class ProductDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        product = Product.objects.filter(slug=slug, is_active=True).first()
        if product is None:
            return Response({"error": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ProductSerializer(product, context=_context(request, [product])).data)


class ProductCategoryListView(APIView):
    """
    GET /api/products/categories/ — drives the filter chips, with a live count per
    category so the app never offers a filter that returns nothing.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        counts = {
            row["category"]: row["total"]
            for row in Product.objects.filter(is_active=True)
            .values("category")
            .annotate(total=models.Count("id"))
        }
        translated = translated_labels(getattr(request.user, "language", "en") or "en")
        labels = {code: translated.get(name, name) for code, name in Product.CATEGORY_CHOICES}
        kind_labels = {code: translated.get(name, name) for code, name in Product.KIND_CHOICES}

        return Response([
            {
                "kind": kind,
                "kind_display": kind_labels[kind],
                "categories": [
                    {"code": code, "name": labels[code], "count": counts.get(code, 0)}
                    for code in categories
                ],
            }
            for kind, categories in Product.CATEGORIES_BY_KIND.items()
        ])
