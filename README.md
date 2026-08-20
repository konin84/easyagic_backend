# EasyAgric — API Backend pour l'Agriculture Intelligente en Afrique

EasyAgric est une API REST construite avec **Django / Django REST Framework** et déployée sur une base de données **Neon PostgreSQL**. Elle est conçue comme le backend d'une application mobile destinée aux agriculteurs africains.

---

## Fonctionnalités principales

### 1. Analyse de sol par IA (`/advisor/`)

Le cœur du projet. Le fermier envoie une photo de son sol et ses coordonnées GPS. L'API :

- Analyse l'image avec **Google Gemini 2.0 Flash** pour identifier le type de sol, la texture, l'humidité, la fertilité, les problèmes visibles, etc.
- Récupère en parallèle les données météo et pédologiques via **Open-Meteo** (API gratuite)
- Retourne des recommandations de cultures adaptées au sol et à la température actuelle
- Sauvegarde l'analyse, envoie un email au fermier et une notification push sur son appareil — le tout en arrière-plan sans bloquer la réponse

### 2. Recommandations de cultures (`/crops/`)

Recommande des cultures selon le type de sol et la température, à partir d'une base de données locale.

### 3. Météo agricole (`/weather/`)

Données météo enrichies : température du sol à différentes profondeurs, humidité du sol, évapotranspiration, prévisions sur 7 jours.

### 4. Notifications push (`/notifications/`)

Gestion des tokens d'appareils et envoi de notifications push.

### 5. Historique des analyses (`/history/`)

Chaque analyse est enregistrée en base et consultable via le tableau de bord.

### 6. Tableau de bord (`/dashboard/`)

Statistiques agrégées pour les administrateurs et app managers.

### 7. Abonnements (`/subscriptions/`)

À l'inscription, chaque fermier reçoit automatiquement un **essai gratuit de 14 jours limité à 5 analyses d'images**. Une fois l'essai expiré — par la date ou par le quota — les endpoints d'analyse (`/advisor/` et `/soil/analyze/`) répondent **402 Payment Required** avec le nombre de jours et de crédits restants, jusqu'au passage à un plan payant.

- Un crédit n'est décompté **que si l'analyse a réussi** : une panne de Gemini ne coûte rien au fermier
- Les admins et app managers ne sont jamais décomptés
- `GET /api/subscriptions/me/` — état de l'abonnement du fermier connecté
- `GET /api/subscriptions/plans/` — plans disponibles
- `POST /api/subscriptions/upgrade/` — passage à un plan payant (admin / app manager)

Durées et quotas configurables via `TRIAL_DAYS` et `TRIAL_ANALYSIS_QUOTA`.

#### Paiement en espèces et par virement bancaire

Pas de passerelle de paiement : les fermiers paient **en espèces** (auprès d'un agent) ou par **virement bancaire**, et un membre de l'équipe confirme la réception de l'argent.

- `GET /api/subscriptions/payment-instructions/?currency=XOF` — tarifs, coordonnées bancaires et contact pour le paiement en espèces
- `POST /api/subscriptions/upgrade-request/` — **le fermier demande à passer à un plan payant**, avant tout paiement. Rien n'est activé : il reste sur son plan actuel et le paywall reste fermé jusqu'à confirmation par l'équipe. La réponse renvoie le montant dû et les coordonnées bancaires.
- `POST /api/subscriptions/payments/` — le fermier déclare un virement déjà effectué (référence + photo du reçu facultative) → statut **pending**
- `POST /api/subscriptions/payments/<id>/confirm/` — admin / app manager confirme → **le plan est activé automatiquement** et le fermier reçoit un email
- `POST /api/subscriptions/payments/<id>/reject/` — rejet avec motif, le plan reste inchangé

Le champ `pending_upgrade` de `/api/subscriptions/me/` expose la demande en attente, pour afficher « Pro — en attente de confirmation » dans l'application.

Quand un agent encaisse lui-même de l'argent, il enregistre le paiement via le même endpoint (avec `email` du fermier) : celui-ci est **confirmé immédiatement**, puisqu'il détient les fonds.

**Multi-devises** : les tarifs (`PlanPrice`) et les coordonnées bancaires (`PaymentAccount`) sont stockés en base, par devise — modifiables depuis l'admin Django sans redéploiement. Un sous-paiement est accepté mais signalé à l'équipe via le champ `shortfall`.

**Amorçage** : un déploiement neuf n'a ni tarif ni compte bancaire, et les endpoints de paiement renvoient alors 404. La commande `seed_payment_config` règle ça :

```bash
cp payment_config.example.json payment_config.json   # puis remplacer toutes les valeurs
python manage.py seed_payment_config --file payment_config.json
```

En production, coller le même JSON dans la variable `PAYMENT_CONFIG_JSON` : la commande tourne automatiquement à chaque déploiement (`render.yaml`), et ne fait rien si la variable est absente.

Une ligne déjà présente n'est **jamais écrasée** — les tarifs modifiés depuis l'admin Django survivent aux redéploiements. Utiliser `--overwrite` pour forcer les valeurs du JSON.

### 8. Gestion des utilisateurs (`/users/`)

- Rôles : `farmer`, `admin`, `app_manager`
- Authentification par OTP (code à 6 chiffres, valable 10 minutes)
- Support de **17 langues africaines** : Swahili, Hausa, Yoruba, Igbo, Amharique, Zulu, Wolof, Lingala, Shona, Dioula, Baoulé, Bambara, Fulani, etc.
- Les emails de conseil sont traduits automatiquement dans la langue de l'utilisateur via **Google Cloud Translation API**

---

## Stack technique

| Composant       | Technologie                    |
|-----------------|-------------------------------|
| Framework       | Django + DRF                  |
| Base de données | Neon PostgreSQL                |
| IA / Vision     | Google Gemini 2.0 Flash        |
| Météo           | Open-Meteo (gratuit)           |
| Emails          | Django email + Google Cloud Translation |
| Auth            | JWT + OTP par email            |
| Serveur WSGI    | Gunicorn                       |

---

## Cible

Application mobile pour **fermiers africains**, d'où l'importance du support multilingue (17 langues) et de la légèreté des réponses API.
