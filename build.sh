#!/usr/bin/env bash
# Exécuté par Render à chaque déploiement (voir render.yaml).
set -o errexit

# Force the use of uv to install packages into Render's active virtual environment
uv pip install -r requirements.txt

# Run your Django management commands safely
python manage.py collectstatic --noinput
python manage.py migrate
python manage.py ensure_superuser