from django.core.management.base import BaseCommand

from apps.products.models import Product
from apps.products.translation import ensure_translations, translated_labels
from apps.users.models import User


class Command(BaseCommand):
    """
    Pré-traduit le catalogue dans les langues demandées.

    Sans cette étape, le premier fermier à ouvrir le catalogue dans une nouvelle
    langue attend l'appel à Google Translate. Par défaut, ne traduit que les
    langues réellement utilisées par des comptes existants — inutile de payer la
    traduction de langues que personne n'a choisies.
    """

    help = "Pré-traduit le nom, la description et l'unité des produits."

    def add_arguments(self, parser):
        parser.add_argument(
            "--languages", help="Codes séparés par des virgules, ex. fr,sw,ha. Défaut : langues des comptes existants.",
        )
        parser.add_argument("--all", action="store_true", help="Toutes les langues supportées.")

    def handle(self, *args, **options):
        if options.get("languages"):
            languages = [code.strip() for code in options["languages"].split(",") if code.strip()]
        elif options["all"]:
            languages = [code for code, _ in User.LANGUAGE_CHOICES]
        else:
            languages = list(
                User.objects.values_list("language", flat=True).distinct()
            )

        languages = [code for code in languages if code and code != "en"]
        if not languages:
            self.stdout.write("Aucune langue à traduire (tout le monde est en anglais).")
            return

        products = list(Product.objects.all())
        for language in languages:
            before = sum(1 for p in products if language in (p.translations or {}))
            ensure_translations(products, language)
            translated_labels(language)
            after = sum(1 for p in products if language in (p.translations or {}))
            status = "déjà à jour" if after == before else f"{after - before} produit(s) traduit(s)"
            self.stdout.write(f"  {language}: {status} ({after}/{len(products)})")

        self.stdout.write(self.style.SUCCESS(f"Traduction terminée pour : {', '.join(languages)}"))
