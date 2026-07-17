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

### 7. Gestion des utilisateurs (`/users/`)

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
