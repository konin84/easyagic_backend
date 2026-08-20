from django.apps import AppConfig


class ProductsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.products"

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_seed_catalogue, sender=self)


def _seed_catalogue(sender, **kwargs):
    """
    Seed the catalogue whenever migrations run, mirroring how `apps.users` creates
    the default admin.

    Hanging this off `migrate` rather than the deploy's start command matters:
    `render.yaml` is only authoritative for Blueprint-managed services, so a start
    command edited there silently does nothing on a dashboard-created service.
    `migrate` always runs, so this always runs.

    The command is create-not-overwrite, so this never disturbs edits made in
    Django admin and never duplicates a product.
    """
    from django.core.management import call_command

    try:
        call_command("seed_products", verbosity=1)
    except Exception as exc:  # never let seeding break a deploy
        # Printed, not swallowed: this line is the only signal in the deploy log
        # when the catalogue fails to seed.
        print(f"[EasyAgric] PRODUCT CATALOGUE SEEDING FAILED — {type(exc).__name__}: {exc}")
