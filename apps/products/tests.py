import json
import tempfile
from unittest.mock import patch
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.users.models import User

from .models import Product

SEED_FILE = Path("apps/products/data/products.json")


class SeedProductsTests(TestCase):
    def seed(self, payload=None, **options):
        out = StringIO()
        if payload is None:
            call_command("seed_products", stdout=out, no_images=True, **options)
        else:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "p.json"
                path.write_text(json.dumps({"products": payload}))
                call_command("seed_products", file=str(path), stdout=out, no_images=True, **options)
        return out.getvalue()

    def test_bundled_catalogue_seeds(self):
        self.seed()

        total = Product.objects.count()
        self.assertGreaterEqual(total, 40)
        self.assertTrue(Product.objects.filter(kind=Product.INPUT).exists())
        self.assertTrue(Product.objects.filter(kind=Product.PRODUCE).exists())

    def test_every_category_is_represented(self):
        self.seed()

        seeded = set(Product.objects.values_list("category", flat=True))
        expected = {code for code, _ in Product.CATEGORY_CHOICES}
        self.assertEqual(seeded, expected, "every filter chip must return products")

    def test_every_product_has_a_description_and_unit(self):
        self.seed()

        for product in Product.objects.all():
            self.assertTrue(product.description.strip(), f"{product.name} has no description")
            self.assertTrue(product.unit.strip(), f"{product.name} has no unit")

    def test_slugs_are_generated_and_unique(self):
        self.seed()

        slugs = list(Product.objects.values_list("slug", flat=True))
        self.assertTrue(all(slugs))
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_rerunning_is_idempotent_and_keeps_admin_edits(self):
        self.seed()
        count = Product.objects.count()
        Product.objects.filter(name="Maize").update(description="Edited by ops")

        output = self.seed()

        self.assertEqual(Product.objects.count(), count)
        self.assertEqual(Product.objects.get(name="Maize").description, "Edited by ops")
        self.assertIn("inchangé", output)

    def test_overwrite_restores_the_json_values(self):
        self.seed()
        Product.objects.filter(name="Maize").update(description="Edited by ops")

        self.seed(overwrite=True)

        self.assertNotEqual(Product.objects.get(name="Maize").description, "Edited by ops")

    # ------------------------------------------------------------- validation

    def test_category_must_belong_to_the_kind(self):
        payload = [{"name": "Wrong", "kind": "input", "category": "grain", "description": "x"}]
        with self.assertRaisesMessage(CommandError, "n'appartient pas au type"):
            self.seed(payload)

    def test_unknown_kind_is_rejected(self):
        payload = [{"name": "Wrong", "kind": "livestock", "category": "grain", "description": "x"}]
        with self.assertRaisesMessage(CommandError, "type 'livestock' inconnu"):
            self.seed(payload)

    def test_missing_description_is_rejected(self):
        payload = [{"name": "Bare", "kind": "produce", "category": "grain", "description": "  "}]
        with self.assertRaisesMessage(CommandError, "description est obligatoire"):
            self.seed(payload)


class ProductAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_products", stdout=StringIO(), no_images=True)

    def setUp(self):
        self.client = APIClient()
        self.farmer = User.objects.create_user(
            username="p@example.com", email="p@example.com", password="x" * 12, role=User.FARMER,
        )
        self.client.force_authenticate(user=self.farmer)

    def test_listing_requires_authentication(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(reverse("product-list")).status_code, 401)

    def test_list_returns_paginated_catalogue(self):
        response = self.client.get(reverse("product-list"))

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 40)
        row = response.data["results"][0]
        self.assertEqual(
            set(row),
            {"id", "slug", "name", "kind", "kind_display", "category",
             "category_display", "description", "unit", "image", "image_credit"},
        )

    def test_filter_by_kind(self):
        response = self.client.get(reverse("product-list"), {"kind": Product.PRODUCE, "limit": 200})
        kinds = {r["kind"] for r in response.data["results"]}
        self.assertEqual(kinds, {Product.PRODUCE})

    def test_filter_by_category(self):
        response = self.client.get(reverse("product-list"), {"category": Product.SEED, "limit": 200})
        self.assertTrue(response.data["results"])
        self.assertEqual({r["category"] for r in response.data["results"]}, {Product.SEED})

    def test_search_matches_name_and_description(self):
        response = self.client.get(reverse("product-list"), {"search": "cassava", "limit": 200})
        names = " ".join(r["name"].lower() for r in response.data["results"])
        self.assertIn("cassava", names)

    def test_inactive_products_are_hidden(self):
        product = Product.objects.first()
        product.is_active = False
        product.save(update_fields=["is_active"])

        response = self.client.get(reverse("product-list"), {"limit": 200})
        self.assertNotIn(product.slug, [r["slug"] for r in response.data["results"]])

    def test_detail_by_slug(self):
        product = Product.objects.get(name="Yam")
        response = self.client.get(reverse("product-detail", args=[product.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Yam")
        self.assertTrue(response.data["description"])

    def test_missing_product_is_404(self):
        self.assertEqual(
            self.client.get(reverse("product-detail", args=["no-such-thing"])).status_code, 404
        )

    def test_image_url_is_used_when_there_is_no_uploaded_file(self):
        product = Product.objects.first()
        product.image.delete(save=False)
        product.image = None
        product.image_url = "https://cdn.example.com/maize.jpg"
        product.save(update_fields=["image", "image_url"])

        response = self.client.get(reverse("product-detail", args=[product.slug]))
        self.assertEqual(response.data["image"], "https://cdn.example.com/maize.jpg")

    def test_image_is_null_only_when_neither_source_is_set(self):
        product = Product.objects.first()
        product.image.delete(save=False)
        product.image = None
        product.image_url = ""
        product.save(update_fields=["image", "image_url"])

        response = self.client.get(reverse("product-detail", args=[product.slug]))
        self.assertIsNone(response.data["image"])

    def test_categories_endpoint_reports_counts_per_kind(self):
        response = self.client.get(reverse("product-categories"))

        self.assertEqual(response.status_code, 200)
        kinds = {group["kind"] for group in response.data}
        self.assertEqual(kinds, {Product.INPUT, Product.PRODUCE})
        for group in response.data:
            for category in group["categories"]:
                self.assertGreater(category["count"], 0, f"{category['code']} chip would be empty")

    def test_bad_paging_is_rejected(self):
        self.assertEqual(
            self.client.get(reverse("product-list"), {"limit": "lots"}).status_code, 400
        )


class ProductImageTests(TestCase):
    """Generated artwork, so no product renders as a broken tile."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.media = override_settings(MEDIA_ROOT=self.tmp.name)
        self.media.enable()
        self.addCleanup(self.media.disable)
        # post_migrate already seeded this test DB; start clean so each test
        # controls exactly which products and images exist
        Product.objects.all().delete()

    def seed(self, **options):
        call_command("seed_products", stdout=StringIO(), **options)

    def test_every_seeded_product_gets_an_image(self):
        self.seed()

        self.assertTrue(Product.objects.exists())
        missing = [p.name for p in Product.objects.all() if not p.display_image]
        self.assertEqual(missing, [], "these products would render as broken tiles")

    def test_images_are_backfilled_onto_products_that_predate_them(self):
        """The live catalogue was seeded before artwork existed — it must fill in."""
        self.seed(no_images=True)
        self.assertFalse(any(p.image for p in Product.objects.all()))
        count = Product.objects.count()

        self.seed()

        self.assertEqual(Product.objects.count(), count, "backfilling must not duplicate rows")
        # products with a licensed photo need no card; the rest must have got one
        self.assertTrue(all(p.display_image for p in Product.objects.all()))
        self.assertTrue(all(p.image for p in Product.objects.filter(image_url="")))

    def test_rerunning_does_not_regenerate_existing_images(self):
        self.seed()
        before = {p.slug: p.image.name for p in Product.objects.all()}

        self.seed()

        after = {p.slug: p.image.name for p in Product.objects.all()}
        self.assertEqual(before, after)

    def test_a_real_uploaded_photo_is_never_replaced(self):
        self.seed(no_images=True)
        product = Product.objects.get(name="Cocoa")
        product.image.save("real-cocoa.jpg", ContentFile(b"pretend-photo"), save=True)

        self.seed()
        self.seed(regenerate_images=True)

        product.refresh_from_db()
        self.assertIn("real-cocoa", product.image.name)
        self.assertEqual(product.image.read(), b"pretend-photo")

    def test_generated_image_is_a_real_jpeg_of_the_right_size(self):
        from PIL import Image as PILImage

        self.seed()
        product = Product.objects.first()

        with product.image.open("rb") as handle:
            img = PILImage.open(handle)
            self.assertEqual(img.format, "JPEG")
            self.assertEqual(img.size, (800, 600))

    def test_categories_get_distinct_colours(self):
        """A farmer should be able to tell categories apart at a glance."""
        from apps.products.images import PALETTE

        self.assertEqual(
            len(PALETTE), len(Product.CATEGORY_CHOICES), "every category needs a colour"
        )
        grounds = [ground for ground, _ in PALETTE.values()]
        self.assertEqual(len(grounds), len(set(grounds)), "colours must be distinct")

    def test_api_serves_the_image_url(self):
        self.seed()
        farmer = User.objects.create_user(
            username="img@example.com", email="img@example.com",
            password="x" * 12, role=User.FARMER,
        )
        client = APIClient()
        client.force_authenticate(user=farmer)

        response = client.get(reverse("product-list"))
        images = [r["image"] for r in response.data["results"]]

        self.assertTrue(all(images), "the app must get an image for every product")
        self.assertTrue(images[0].startswith("http"), "must be an absolute URL for the app")

    def test_missing_font_does_not_break_generation(self):
        """Render's container may not ship DejaVu — fall back rather than fail."""
        from apps.products import images as images_module

        with patch.object(images_module, "_FONT_CANDIDATES", ["/nope/missing.ttf"]):
            content = images_module.build_placeholder("Maize", "grain", "Grains & Cereals")

        self.assertGreater(len(content.read()), 0)


class StorageBackendTests(TestCase):
    """
    Guards the failure that shipped a catalogue of null images to production:
    settings switch media storage to Cloudinary whenever CLOUDINARY_CLOUD_NAME is
    set, but the package was never declared as a dependency, so every save raised.
    """

    def test_cloudinary_backend_is_importable(self):
        """The exact failure: 'No module named cloudinary_storage' on every save."""
        import importlib.util

        # find_spec, not import: the module raises ImproperlyConfigured at import
        # time when credentials are absent. What broke production was the package
        # being missing entirely.
        self.assertIsNotNone(
            importlib.util.find_spec("cloudinary_storage"),
            "cloudinary_storage is not installed — every media save in production will fail",
        )
        self.assertIsNotNone(importlib.util.find_spec("cloudinary"))

    def test_whitenoise_static_backend_is_importable(self):
        from django.core.files.storage import InvalidStorageError, storages

        try:
            storages["staticfiles"]
        except InvalidStorageError as exc:
            self.fail(f"staticfiles storage cannot load, collectstatic would fail: {exc}")

    def test_storage_packages_are_declared_in_requirements(self):
        """They were installed on Render only as leftovers from an older build."""
        requirements = Path("requirements.txt").read_text().lower()
        for package in ("cloudinary", "django-cloudinary-storage", "whitenoise"):
            self.assertIn(package, requirements, f"{package} is used but not pinned")


class ImagePrecedenceTests(TestCase):
    """A real photo beats a licensed URL beats a generated card."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        media = override_settings(MEDIA_ROOT=self.tmp.name)
        media.enable()
        self.addCleanup(media.disable)
        Product.objects.all().delete()
        call_command("seed_products", stdout=StringIO())

    def test_no_product_is_ever_imageless(self):
        missing = [p.name for p in Product.objects.all() if not p.display_image]
        self.assertEqual(missing, [])

    def test_most_products_carry_a_licensed_photo(self):
        with_photo = Product.objects.exclude(image_url="").count()
        self.assertGreaterEqual(with_photo, 30)

    def test_products_without_a_photo_fall_back_to_generated_art(self):
        for product in Product.objects.filter(image_url=""):
            self.assertTrue(product.image, f"{product.name} has neither photo nor card")
            self.assertTrue(product.image_is_placeholder)

    def test_no_generated_card_is_made_when_a_photo_url_exists(self):
        """Generating art for a product that already has a photo wastes storage."""
        for product in Product.objects.exclude(image_url=""):
            self.assertFalse(product.image, f"{product.name} has a redundant generated card")

    def test_photo_url_wins_over_a_generated_card(self):
        product = Product.objects.filter(image_url="").first()
        self.assertTrue(product.image_is_placeholder)

        product.image_url = "https://cdn.example.com/real.jpg"
        product.save(update_fields=["image_url"])

        self.assertEqual(product.display_image, "https://cdn.example.com/real.jpg")
        self.assertFalse(product.image_is_placeholder)

    def test_uploaded_photo_wins_over_everything(self):
        product = Product.objects.exclude(image_url="").first()
        product.image.save("real.jpg", ContentFile(b"photo"), save=True)

        self.assertTrue(product.display_image.endswith(".jpg"))
        self.assertNotEqual(product.display_image, product.image_url)

    def test_every_photo_carries_its_licence_attribution(self):
        """CC BY-SA requires credit — an unattributed photo is a licence breach."""
        for product in Product.objects.exclude(image_url=""):
            self.assertTrue(
                product.image_credit.strip(),
                f"{product.name} has a photo with no attribution",
            )

    def test_api_exposes_image_and_credit(self):
        farmer = User.objects.create_user(
            username="c@example.com", email="c@example.com", password="x" * 12, role=User.FARMER,
        )
        client = APIClient()
        client.force_authenticate(user=farmer)

        response = client.get(reverse("product-list"), {"limit": 200})
        rows = response.data["results"]

        self.assertTrue(all(r["image"] for r in rows))
        for row in rows:
            if row["image"].startswith("https://upload.wikimedia.org"):
                self.assertTrue(row["image_credit"], f"{row['name']} missing credit")

    def test_seed_urls_are_https(self):
        payload = json.loads(Path("apps/products/data/products.json").read_text())
        for product in payload["products"]:
            url = product.get("image_url") or ""
            if url:
                self.assertTrue(url.startswith("https://"), f"{product['name']} is not https")


class BackfillExistingCatalogueTests(TestCase):
    """
    Regression: the live catalogue was seeded before photos existed, and
    create-not-overwrite meant a later deploy silently withheld every image_url,
    leaving the app showing null images.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        media = override_settings(MEDIA_ROOT=self.tmp.name)
        media.enable()
        self.addCleanup(media.disable)

        Product.objects.all().delete()
        call_command("seed_products", stdout=StringIO(), no_images=True)
        # rewind to the state production was actually in
        Product.objects.update(image_url="", image_credit="")

    def seed(self, **options):
        call_command("seed_products", stdout=StringIO(), **options)

    def test_plain_reseed_backfills_photo_urls(self):
        """Must work WITHOUT --overwrite, since deploys never pass it."""
        self.assertEqual(Product.objects.exclude(image_url="").count(), 0)

        self.seed()

        self.assertGreaterEqual(Product.objects.exclude(image_url="").count(), 30)

    def test_backfill_leaves_no_product_imageless(self):
        self.seed()
        self.assertEqual([p.name for p in Product.objects.all() if not p.display_image], [])

    def test_backfill_brings_the_licence_credit_with_the_photo(self):
        self.seed()
        for product in Product.objects.exclude(image_url=""):
            self.assertTrue(product.image_credit.strip(), f"{product.name} photo lacks attribution")

    def test_backfill_never_overwrites_a_url_someone_chose(self):
        product = Product.objects.get(name="Cocoa")
        product.image_url = "https://ops.example.com/cocoa.jpg"
        product.save(update_fields=["image_url"])

        self.seed()

        product.refresh_from_db()
        self.assertEqual(product.image_url, "https://ops.example.com/cocoa.jpg")

    def test_backfill_does_not_touch_edited_descriptions(self):
        Product.objects.filter(name="Cocoa").update(description="Reworded by ops")

        self.seed()

        self.assertEqual(Product.objects.get(name="Cocoa").description, "Reworded by ops")

    def test_backfill_is_stable_across_repeated_deploys(self):
        self.seed()
        first = {p.slug: (p.image_url, p.image_credit) for p in Product.objects.all()}

        self.seed()
        self.seed()

        after = {p.slug: (p.image_url, p.image_credit) for p in Product.objects.all()}
        self.assertEqual(first, after)
        self.assertEqual(Product.objects.count(), len(first))
