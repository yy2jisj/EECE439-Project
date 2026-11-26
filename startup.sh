#!/bin/bash
set -e

# keep the online database outside the deployed code
mkdir -p "$(dirname "${DJANGO_DB_PATH:-db.sqlite3}")"
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn website.wsgi:application --bind 0.0.0.0:8000 --workers 1 --threads 2 --timeout 120
