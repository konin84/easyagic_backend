#!/usr/bin/env bash
# Exécuté par Render à chaque déploiement (voir render.yaml).
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate
python manage.py ensure_superuser
