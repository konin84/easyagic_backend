from django.db import migrations

# Products dropped from the catalogue because no suitable freely-licensed photo
# could be found for them. The seeder never deletes rows, so removing them from
# products.json is not enough — databases already seeded need this.
REMOVED_SLUGS = [
    "urea-46-0-0",
    "poultry-manure-pellets",
    "agricultural-lime",
    "foliar-micronutrient-spray",
    "broad-spectrum-insecticide",
    "selective-herbicide",
    "treadle-pump",
    "maize",
    "irish-potato",
    "cowpea-beans",
]


def remove_imageless(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    Product.objects.filter(slug__in=REMOVED_SLUGS).delete()


def noop(apps, schema_editor):
    """Irreversible by design — re-running seed_products restores anything wanted back."""


class Migration(migrations.Migration):
    dependencies = [("products", "0002_product_image_credit_alter_product_image_url")]

    operations = [migrations.RunPython(remove_imageless, noop)]
