from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_create_default_admin, sender=self)


def _create_default_admin(sender, **kwargs):
    from django.contrib.auth import get_user_model
    from decouple import config

    User = get_user_model()

    if User.objects.filter(role=User.ADMIN).exists():
        return

    email = config("ADMIN_EMAIL", default="admin@easyagric.com")
    password = config("ADMIN_PASSWORD", default="admin1234")

    User.objects.create_superuser(
        username=email,
        email=email,
        password=password,
        role=User.ADMIN,
    )
    print(f"\n[EasyAgric] Default admin created — email: {email}")
    print(f"[EasyAgric] Change the password immediately in production!\n")
