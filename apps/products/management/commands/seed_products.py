import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.products.images import GENERATED_PREFIX, build_placeholder
from apps.products.models import Product

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "products.json"


class Command(BaseCommand):
    """
    Amorce le catalogue de produits agricoles depuis un fichier JSON.

    Par défaut, lit `apps/products/data/products.json`. Comme
    `seed_payment_config`, la commande est idempotente et n'écrase PAS une fiche
    déjà en base : le catalogue s'amorce au démarrage, puis se gère depuis
    l'admin Django (descriptions, images) sans être écrasé au redéploiement.
    Utiliser --overwrite pour forcer les valeurs du JSON.

    Une image de remplacement est générée pour toute fiche qui n'en a aucune —
    y compris les fiches déjà en base, afin qu'un catalogue existant sans images
    soit complété sans écraser le reste. Toute vraie photo téléversée est
    conservée. Utiliser --no-images pour ne rien générer.
    """

    help = "Amorce le catalogue de produits agricoles (apps/products/data/products.json)."

    FIELDS = ["kind", "category", "description", "unit", "image_url", "image_credit"]

    def add_arguments(self, parser):
        parser.add_argument("--file", help="Chemin d'un fichier JSON de produits.")
        parser.add_argument(
            "--overwrite", action="store_true",
            help="Met à jour les fiches existantes au lieu de les laisser intactes.",
        )
        parser.add_argument(
            "--no-images", action="store_true",
            help="N'génère aucune image de remplacement.",
        )
        parser.add_argument(
            "--regenerate-images", action="store_true",
            help="Régénère les images de remplacement (les vraies photos sont conservées).",
        )

    def handle(self, *args, **options):
        path = Path(options["file"]) if options.get("file") else DEFAULT_DATA
        if not path.exists():
            raise CommandError(f"Fichier introuvable : {path}")

        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise CommandError(f"JSON invalide : {exc}") from exc

        rows = payload.get("products") if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or not rows:
            raise CommandError('Le JSON doit contenir une liste "products" non vide.')

        valid_kinds = {k for k, _ in Product.KIND_CHOICES}
        valid_categories = {c for c, _ in Product.CATEGORY_CHOICES}

        created = updated = skipped = imaged = 0
        for index, row in enumerate(rows):
            name = (row.get("name") or "").strip()
            if not name:
                raise CommandError(f"products[{index}] : le nom est obligatoire.")

            kind, category = row.get("kind"), row.get("category")
            if kind not in valid_kinds:
                raise CommandError(f"products[{index}] ({name}) : type '{kind}' inconnu.")
            if category not in valid_categories:
                raise CommandError(f"products[{index}] ({name}) : catégorie '{category}' inconnue.")
            if category not in Product.CATEGORIES_BY_KIND[kind]:
                raise CommandError(
                    f"products[{index}] ({name}) : la catégorie '{category}' n'appartient pas au type '{kind}'."
                )
            if not (row.get("description") or "").strip():
                raise CommandError(f"products[{index}] ({name}) : la description est obligatoire.")

            values = {field: row.get(field, "") or "" for field in self.FIELDS}
            values["kind"], values["category"] = kind, category

            existing = Product.objects.filter(slug=slugify(name)[:140]).first()
            if existing is None:
                product = Product.objects.create(name=name, is_active=True, **values)
                if self._attach_image(product, options):
                    imaged += 1
                created += 1
                continue

            # Backfill artwork onto rows that predate it, without touching their text
            if self._attach_image(existing, options):
                imaged += 1

            if not options["overwrite"]:
                skipped += 1
                continue

            for field, value in values.items():
                setattr(existing, field, value)
            existing.name = name
            existing.save()
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Catalogue amorcé — {created} créé(s), {updated} mis à jour, {skipped} inchangé(s), "
            f"{imaged} image(s) générée(s)."
        ))
        if skipped and not options["overwrite"]:
            self.stdout.write("Utiliser --overwrite pour forcer les valeurs du JSON.")

    def _attach_image(self, product, options):
        """
        Give the product a generated card if it has none. Returns True when one
        was written.

        A real photo uploaded through Django admin is NEVER replaced, not even by
        --regenerate-images: generated art is written under `products/generated/`,
        so anything outside that prefix is treated as a genuine upload.
        """
        if options.get("no_images"):
            return False
        # A licensed photo makes the generated card unnecessary
        if product.image_url:
            return False

        if product.image:
            is_generated = product.image.name.startswith(GENERATED_PREFIX)
            if not (is_generated and options.get("regenerate_images")):
                return False

        try:
            content = build_placeholder(
                product.name, product.category, product.get_category_display()
            )
        except Exception as exc:
            # Loud on purpose: a silently swallowed storage error once made a
            # broken production deploy look like a successful one.
            self.stderr.write(
                f"  ! IMAGE FAILED for {product.name} — {type(exc).__name__}: {exc}"
            )
            return False

        product.image.save(f"generated/{product.slug}.jpg", content, save=True)
        return True
