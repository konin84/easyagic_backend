import unicodedata

from django.db import models

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Product
from .serializers import ProductSerializer
from .translation import ensure_translations, translated_labels


def _sort_key(name):
    """
    Sort key that ignores accents, so \u00c9quipement files under E rather than after Z.
    Matters once category names are translated into French, Spanish or Portuguese.
    """
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFKD", name) if not unicodedata.combining(ch)
    )
    return stripped.casefold()


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


class ProductsByCategoryView(APIView):
    """
    GET /api/products/by-category/ — the whole catalogue, grouped.

    ?group_by=kind   (default) nested: each kind with its categories, categories
                     in curated order (seeds before fertiliser, grains before
                     cash crops) rather than alphabetical
    ?group_by=name   flat: every category in one array, sorted by its translated
                     name, each carrying `kind` so the app can still badge it

    ?kind=input|produce            restrict to one family
    ?limit_per_category=4          cap products per group, for a home screen
                                   showing a few per section with "see all"
    ?include_empty=true            keep categories that have no products
    """

    permission_classes = [IsAuthenticated]

    MAX_PER_CATEGORY = 100
    GROUPINGS = ("kind", "name")

    def get(self, request):
        group_by = request.query_params.get("group_by", "kind").lower()
        if group_by not in self.GROUPINGS:
            return Response(
                {"error": f"Unknown group_by '{group_by}'. Use kind or name."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        kind = request.query_params.get("kind")
        if kind and kind not in dict(Product.KIND_CHOICES):
            return Response(
                {"error": f"Unknown kind '{kind}'. Use input or produce."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_limit = request.query_params.get("limit_per_category")
        limit = None
        if raw_limit is not None:
            try:
                limit = int(raw_limit)
            except ValueError:
                return Response(
                    {"error": "limit_per_category must be a whole number."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            limit = max(1, min(limit, self.MAX_PER_CATEGORY))

        include_empty = request.query_params.get("include_empty", "").lower() in ("1", "true", "yes")

        products = Product.objects.filter(is_active=True)
        if kind:
            products = products.filter(kind=kind)
        products = list(products)

        context = _context(request, products)
        labels = context["labels"]
        category_names = dict(Product.CATEGORY_CHOICES)
        kind_names = dict(Product.KIND_CHOICES)

        grouped = {}
        for product in products:
            grouped.setdefault(product.category, []).append(product)

        def build(kind_code, code):
            rows = grouped.get(code, [])
            english = category_names[code]
            return {
                "code": code,
                "name": labels.get(english, english),
                "kind": kind_code,
                "kind_display": labels.get(kind_names[kind_code], kind_names[kind_code]),
                "count": len(rows),
                "products": ProductSerializer(
                    rows[:limit] if limit else rows, many=True, context=context
                ).data,
            }

        categories = [
            build(kind_code, code)
            for kind_code, codes in Product.CATEGORIES_BY_KIND.items()
            if not kind or kind_code == kind
            for code in codes
            if grouped.get(code) or include_empty
        ]

        if group_by == "name":
            return Response(sorted(categories, key=lambda c: _sort_key(c["name"])))

        payload = []
        for kind_code in Product.CATEGORIES_BY_KIND:
            if kind and kind_code != kind:
                continue
            in_kind = [c for c in categories if c["kind"] == kind_code]
            if not in_kind and not include_empty:
                continue
            payload.append({
                "kind": kind_code,
                "kind_display": labels.get(kind_names[kind_code], kind_names[kind_code]),
                "count": sum(c["count"] for c in in_kind),
                # `kind` and `kind_display` are on the parent here, so drop them
                # from each child rather than repeating them 12 times
                "categories": [
                    {k: v for k, v in c.items() if k not in ("kind", "kind_display")}
                    for c in in_kind
                ],
            })

        return Response(payload)
