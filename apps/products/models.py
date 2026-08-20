from django.db import models
from django.utils.text import slugify

from .images import GENERATED_PREFIX


class Product(models.Model):
    """
    Catalogue entry shown in the app.

    Two kinds share one table: INPUT is what a farmer buys to grow (seed,
    fertiliser, tools), PRODUCE is what they grow and sell. `kind` is the coarse
    split the app uses for its two tabs; `category` drives the filter chips.
    """

    INPUT = "input"
    PRODUCE = "produce"
    KIND_CHOICES = [
        (INPUT, "Farm Input"),
        (PRODUCE, "Produce"),
    ]

    # Input categories
    SEED = "seed"
    FERTILIZER = "fertilizer"
    CROP_PROTECTION = "crop_protection"
    TOOL = "tool"
    IRRIGATION = "irrigation"
    PROTECTIVE_EQUIPMENT = "protective_equipment"
    # Produce categories
    GRAIN = "grain"
    TUBER = "tuber"
    LEGUME = "legume"
    VEGETABLE = "vegetable"
    FRUIT = "fruit"
    CASH_CROP = "cash_crop"

    CATEGORY_CHOICES = [
        (SEED, "Seeds & Planting Material"),
        (FERTILIZER, "Fertilisers & Soil Amendments"),
        (CROP_PROTECTION, "Crop Protection"),
        (TOOL, "Tools & Equipment"),
        (IRRIGATION, "Irrigation"),
        (PROTECTIVE_EQUIPMENT, "Protective Equipment"),
        (GRAIN, "Grains & Cereals"),
        (TUBER, "Roots & Tubers"),
        (LEGUME, "Legumes & Pulses"),
        (VEGETABLE, "Vegetables"),
        (FRUIT, "Fruits"),
        (CASH_CROP, "Cash Crops"),
    ]

    CATEGORIES_BY_KIND = {
        INPUT: [SEED, FERTILIZER, CROP_PROTECTION, TOOL, IRRIGATION, PROTECTIVE_EQUIPMENT],
        PRODUCE: [GRAIN, TUBER, LEGUME, VEGETABLE, FRUIT, CASH_CROP],
    }

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES)
    description = models.TextField(help_text="A couple of practical sentences for the farmer.")
    unit = models.CharField(
        max_length=60, blank=True, help_text="How it is sold, e.g. '50 kg bag' or 'per kg'."
    )
    image = models.ImageField(upload_to="products/", null=True, blank=True)
    image_url = models.URLField(
        blank=True, help_text="Freely-licensed photo, used in preference to a generated card."
    )
    image_credit = models.CharField(
        max_length=255, blank=True,
        help_text="Attribution required by the photo's licence. Show it wherever the image is displayed.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "category", "name"]
        indexes = [models.Index(fields=["kind", "category"])]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)

    @property
    def display_image(self):
        """
        Best available artwork, in order: a real photo someone uploaded, then a
        licensed photo URL, then the generated placeholder card. None only if the
        product somehow has all three missing.
        """
        if self.image and not self.image.name.startswith(GENERATED_PREFIX):
            return self.image.url
        if self.image_url:
            return self.image_url
        if self.image:
            return self.image.url
        return None

    @property
    def image_is_placeholder(self):
        """True while this product is still showing generated art rather than a photo."""
        return self.display_image is not None and not self.image_url and bool(self.image)
