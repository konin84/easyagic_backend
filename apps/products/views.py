import unicodedata

from django.db import models

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Product
from .serializers import ProductSerializer
from .translation import ensure_translations, translated_labels


GROUPINGS = {
    "kind": (True, False),        # nested by kind, curated category order
    "name": (False, True),        # flat, categories A-Z
    "kind,name": (True, True),    # nested by kind, categories A-Z inside each
}


def resolve_category(value, labels):
    """
    Turn whatever the app sends into a category code.

    Accepts the code (`cash_crop`), the English label (`Cash Crops`), or the
    label as the farmer sees it translated (`Cultures de rente`) — so a UI that
    only holds the display name does not have to map it back to a code. Matching
    ignores case and surrounding space. Returns None if nothing matches.
    """
    if not value:
        return None

    needle = value.strip().casefold()

    for code, _ in Product.CATEGORY_CHOICES:
        if code.casefold() == needle:
            return code

    for code, english in Product.CATEGORY_CHOICES:
        if english.casefold() == needle:
            return code
        translated = labels.get(english)
        if translated and translated.casefold() == needle:
            return code

    return None


def parse_group_by(value):
    """
    Returns (nest_by_kind, sort_by_name), or None if the value is not understood.

    `kind,name` is the composition: group by kind first, then order the
    categories inside each kind by name.
    """
    key = ",".join(part.strip() for part in (value or "kind").lower().split(",") if part.strip())
    if key == "name,kind":
        key = "kind,name"
    return GROUPINGS.get(key)


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

    Filters: ?kind=input|produce,
             ?category=  the code (cash_crop), the English label (Cash Crops), or
                         the label as the farmer sees it translated,
             ?search=<name or description>
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
            labels = translated_labels(getattr(request.user, "language", "en") or "en")
            code = resolve_category(category, labels)
            if code is None:
                return Response(
                    {
                        "error": f"Unknown category '{category}'.",
                        "valid_categories": [
                            {"code": c, "name": labels.get(n, n)}
                            for c, n in Product.CATEGORY_CHOICES
                        ],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            products = products.filter(category=code)

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
        grouping = parse_group_by(request.query_params.get("group_by"))
        if grouping is None:
            return Response(
                {"error": "group_by must be kind, name, or kind,name."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        nest_by_kind, sort_by_name = grouping

        translated = translated_labels(getattr(request.user, "language", "en") or "en")
        labels = {code: translated.get(name, name) for code, name in Product.CATEGORY_CHOICES}
        kind_labels = {code: translated.get(name, name) for code, name in Product.KIND_CHOICES}

        def entries(kind_code):
            rows = [
                {"code": code, "name": labels[code], "count": counts.get(code, 0)}
                for code in Product.CATEGORIES_BY_KIND[kind_code]
            ]
            return sorted(rows, key=lambda c: _sort_key(c["name"])) if sort_by_name else rows

        if not nest_by_kind:
            flat = [
                {**row, "kind": kind_code, "kind_display": kind_labels[kind_code]}
                for kind_code in Product.CATEGORIES_BY_KIND
                for row in entries(kind_code)
            ]
            return Response(sorted(flat, key=lambda c: _sort_key(c["name"])))

        return Response([
            {
                "kind": kind_code,
                "kind_display": kind_labels[kind_code],
                "categories": entries(kind_code),
            }
            for kind_code in Product.CATEGORIES_BY_KIND
        ])


class ProductsByCategoryView(APIView):
    """
    GET /api/products/by-category/ — the whole catalogue, grouped.

    ?group_by=kind        (default) nested by kind, categories in curated order
                          (seeds before fertiliser, grains before cash crops)
    ?group_by=kind,name   nested by kind, categories sorted A-Z inside each
    ?group_by=name        flat: every category in one array sorted A-Z, each
                          carrying `kind` so the app can still badge it

    Sorting always uses the translated name, so it is alphabetical for the reader.

    ?kind=input|produce            restrict to one family
    ?limit_per_category=4          cap products per group, for a home screen
                                   showing a few per section with "see all"
    ?include_empty=true            keep categories that have no products
    """

    permission_classes = [IsAuthenticated]

    MAX_PER_CATEGORY = 100

    def get(self, request):
        grouping = parse_group_by(request.query_params.get("group_by"))
        if grouping is None:
            return Response(
                {"error": "group_by must be kind, name, or kind,name."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        nest_by_kind, sort_by_name = grouping

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

        if sort_by_name:
            categories.sort(key=lambda c: _sort_key(c["name"]))

        if not nest_by_kind:
            return Response(categories)

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
