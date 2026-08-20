import json
from pathlib import Path

from decouple import config

from django.core.management.base import BaseCommand, CommandError

from apps.subscriptions.models import (
    CURRENCY_CHOICES,
    PaymentAccount,
    PlanPrice,
    Subscription,
)


class Command(BaseCommand):
    """
    Amorce les tarifs (PlanPrice) et les coordonnées bancaires (PaymentAccount)
    à partir d'un JSON, pour qu'un déploiement neuf soit utilisable immédiatement.

    Source du JSON, dans l'ordre : --file, puis la variable PAYMENT_CONFIG_JSON
    (env ou .env, comme FIREBASE_CREDENTIALS_JSON). Si rien n'est fourni, la
    commande ne fait rien — sans danger à exécuter à chaque déploiement.

    Par défaut, une ligne déjà présente n'est PAS écrasée : l'amorçage sert au
    démarrage, ensuite les tarifs se gèrent depuis l'admin Django sans
    redéploiement. Utiliser --overwrite pour forcer les valeurs du JSON.

    Format attendu :
      {
        "prices":   [{"plan": "pro", "currency": "XOF", "amount": 15000}],
        "accounts": [{"currency": "XOF", "bank_name": "...",
                      "account_name": "...", "account_number": "..."}]
      }
    """

    help = "Amorce les tarifs et coordonnées bancaires depuis PAYMENT_CONFIG_JSON ou --file."

    ACCOUNT_FIELDS = [
        "bank_name", "account_name", "account_number", "swift_or_iban", "branch",
        "cash_contact_name", "cash_contact_phone", "instructions",
    ]
    REQUIRED_ACCOUNT_FIELDS = ["bank_name", "account_name", "account_number"]

    def add_arguments(self, parser):
        parser.add_argument("--file", help="Chemin d'un fichier JSON de configuration.")
        parser.add_argument(
            "--overwrite", action="store_true",
            help="Met à jour les lignes existantes au lieu de les laisser intactes.",
        )

    # ------------------------------------------------------------------ entrée

    def handle(self, *args, **options):
        payload = self._load(options.get("file"))
        if payload is None:
            self.stdout.write("PAYMENT_CONFIG_JSON non défini — étape ignorée.")
            return

        prices = payload.get("prices", [])
        accounts = payload.get("accounts", [])
        if not prices and not accounts:
            self.stdout.write("Aucun tarif ni compte dans la configuration — rien à faire.")
            return

        overwrite = options["overwrite"]
        valid_currencies = {code for code, _ in CURRENCY_CHOICES}

        created, updated, skipped = 0, 0, 0
        for index, row in enumerate(prices):
            outcome = self._seed_price(row, index, valid_currencies, overwrite)
            created += outcome == "created"
            updated += outcome == "updated"
            skipped += outcome == "skipped"

        for index, row in enumerate(accounts):
            outcome = self._seed_account(row, index, valid_currencies, overwrite)
            created += outcome == "created"
            updated += outcome == "updated"
            skipped += outcome == "skipped"

        summary = f"Amorçage terminé — {created} créé(s), {updated} mis à jour, {skipped} inchangé(s)."
        self.stdout.write(self.style.SUCCESS(summary))
        if skipped and not overwrite:
            self.stdout.write("Utiliser --overwrite pour forcer les valeurs du JSON.")

    def _load(self, file_path):
        if file_path:
            path = Path(file_path)
            if not path.exists():
                raise CommandError(f"Fichier introuvable : {file_path}")
            raw = path.read_text()
        else:
            raw = config("PAYMENT_CONFIG_JSON", default="").strip()
            if not raw:
                return None

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f"JSON invalide : {exc}") from exc

        if not isinstance(payload, dict):
            raise CommandError('Le JSON doit être un objet avec les clés "prices" et/ou "accounts".')
        return payload

    # ------------------------------------------------------------------ tarifs

    def _seed_price(self, row, index, valid_currencies, overwrite):
        where = f"prices[{index}]"
        plan = row.get("plan")
        currency = (row.get("currency") or "").upper()
        amount = row.get("amount")

        if not Subscription.PLAN_CONFIG.get(plan, {}).get("is_paid"):
            raise CommandError(f"{where} : '{plan}' n'est pas un plan payant.")
        if currency not in valid_currencies:
            raise CommandError(f"{where} : devise '{currency}' inconnue.")
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            raise CommandError(f"{where} : montant '{amount}' invalide.") from None
        if amount <= 0:
            raise CommandError(f"{where} : le montant doit être supérieur à zéro.")

        existing = PlanPrice.objects.filter(plan=plan, currency=currency).first()
        if existing is None:
            PlanPrice.objects.create(plan=plan, currency=currency, amount=amount, is_active=True)
            self.stdout.write(f"  + tarif {plan} {amount:g} {currency}")
            return "created"

        if not overwrite:
            self.stdout.write(f"  = tarif {plan} {currency} déjà présent — inchangé")
            return "skipped"

        existing.amount = amount
        existing.is_active = True
        existing.save(update_fields=["amount", "is_active", "updated_at"])
        self.stdout.write(f"  ~ tarif {plan} {currency} mis à jour → {amount:g}")
        return "updated"

    # ----------------------------------------------------------------- comptes

    def _seed_account(self, row, index, valid_currencies, overwrite):
        where = f"accounts[{index}]"
        currency = (row.get("currency") or "").upper()

        if currency not in valid_currencies:
            raise CommandError(f"{where} : devise '{currency}' inconnue.")
        missing = [f for f in self.REQUIRED_ACCOUNT_FIELDS if not row.get(f)]
        if missing:
            raise CommandError(f"{where} : champ(s) obligatoire(s) manquant(s) — {', '.join(missing)}.")

        values = {field: row.get(field, "") or "" for field in self.ACCOUNT_FIELDS}

        existing = PaymentAccount.objects.filter(currency=currency).first()
        if existing is None:
            PaymentAccount.objects.create(currency=currency, is_active=True, **values)
            self.stdout.write(f"  + compte {currency} ({values['bank_name']})")
            return "created"

        if not overwrite:
            self.stdout.write(f"  = compte {currency} déjà présent — inchangé")
            return "skipped"

        for field, value in values.items():
            setattr(existing, field, value)
        existing.is_active = True
        existing.save()
        self.stdout.write(f"  ~ compte {currency} mis à jour")
        return "updated"
