"""
Catalogue text in the farmer's own language.

Translating on every request would mean ~114 Google Translate segments per list
call, so translations are cached instead: per-product text is stored on the row
in a `translations` JSON column, and the fixed vocabulary (kind and category
labels) sits in Django's cache. The API is therefore hit roughly once per
language, not once per request.
"""

import hashlib
import logging

from django.core.cache import cache

from apps.utils.email_translate import translate_batch

logger = logging.getLogger(__name__)

TRANSLATED_FIELDS = ["name", "description", "unit"]
LABEL_CACHE_SECONDS = 60 * 60 * 24 * 7
# Google's API caps the number of segments per call
CHUNK = 100


def _translate(texts, language):
    """
    Translate a list, or return None if translation did not happen.

    `translate_batch` returns its input unchanged on failure or for an
    unsupported language. Distinguishing that from a real result matters: caching
    the English fallback would make a transient outage permanent.
    """
    if not texts:
        return []

    out = []
    for start in range(0, len(texts), CHUNK):
        chunk = texts[start:start + CHUNK]
        result = translate_batch(chunk, language)
        if result is chunk:  # untouched — failed, or nothing to do
            return None
        out.extend(result)
    return out


def fingerprint(product):
    """Identifies the English text a translation was made from."""
    joined = "\x1f".join(getattr(product, field) or "" for field in TRANSLATED_FIELDS)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def translated_labels(language):
    """`kind_display` / `category_display` values, translated once per language."""
    from .models import Product

    labels = [name for _, name in Product.KIND_CHOICES]
    labels += [name for _, name in Product.CATEGORY_CHOICES]

    if language == "en":
        return {label: label for label in labels}

    key = f"product-labels:{language}"
    cached = cache.get(key)
    if cached:
        return cached

    translated = _translate(labels, language)
    if translated is None:
        return {label: label for label in labels}

    mapping = dict(zip(labels, translated))
    cache.set(key, mapping, LABEL_CACHE_SECONDS)
    return mapping


def ensure_translations(products, language):
    """
    Make sure every product carries text for `language`, translating and storing
    any that are missing. Safe to call on every request — it is a no-op once the
    language has been warmed.
    """
    from .models import Product

    if language == "en":
        return

    # A product whose English text has been edited counts as missing: its cached
    # translations describe wording that no longer exists.
    missing = []
    for product in products:
        current = fingerprint(product)
        if product.translations_source != current:
            product.translations = {}
            product.translations_source = current
            missing.append(product)
        elif language not in (product.translations or {}):
            missing.append(product)

    if not missing:
        return

    payload = []
    for product in missing:
        payload.extend(getattr(product, field) or "" for field in TRANSLATED_FIELDS)

    translated = _translate(payload, language)
    if translated is None:
        logger.warning("Product translation to '%s' unavailable — serving English", language)
        # Still persist the cleared stale text, so nobody is shown wording that
        # no longer matches the English source.
        Product.objects.bulk_update(missing, ["translations", "translations_source"])
        return

    step = len(TRANSLATED_FIELDS)
    for index, product in enumerate(missing):
        values = translated[index * step:(index + 1) * step]
        product.translations = {**(product.translations or {}), language: dict(zip(TRANSLATED_FIELDS, values))}

    Product.objects.bulk_update(missing, ["translations", "translations_source"])


def localized(product, language):
    """The product's text in `language`, falling back to English field by field."""
    if product.translations_source != fingerprint(product):
        stored = {}  # English text changed since translating — do not show stale wording
    else:
        stored = (product.translations or {}).get(language) or {}
    return {
        field: (stored.get(field) or getattr(product, field))
        for field in TRANSLATED_FIELDS
    }
