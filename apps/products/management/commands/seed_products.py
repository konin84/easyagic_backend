import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

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
    """

    help = "Amorce le catalogue de produits agricoles (apps/products/data/products.json)."

    FIELDS = ["kind", "category", "description", "unit", "image_url"]

    def add_arguments(self, parser):
        parser.add_argument("--file", help="Chemin d'un fichier JSON de produits.")
        parser.add_argument(
            "--overwrite", action="store_true",
            help="Met à jour les fiches existantes au lieu de les laisser intactes.",
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

        created = updated = skipped = 0
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
                Product.objects.create(name=name, is_active=True, **values)
                created += 1
                continue

            if not options["overwrite"]:
                skipped += 1
                continue

            for field, value in values.items():
                setattr(existing, field, value)
            existing.name = name
            existing.save()
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Catalogue amorcé — {created} créé(s), {updated} mis à jour, {skipped} inchangé(s)."
        ))
        if skipped and not options["overwrite"]:
            self.stdout.write("Utiliser --overwrite pour forcer les valeurs du JSON.")
