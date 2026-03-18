#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

cd /session_auth

echo "[start] user=$(id -u):$(id -g)"
echo "[start] pwd=$(pwd)"

echo "[start] Waiting for database..."

export POSTGRES_HOST="${POSTGRES_HOST:?POSTGRES_HOST is required}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"

until python - <<'PY'
import os
import psycopg2

psycopg2.connect(
    dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host=os.environ.get("POSTGRES_HOST"),
    port=int(os.environ.get("POSTGRES_PORT", "5432")),
)
print("db ok")
PY
do
  echo "[start] DB not ready, sleeping..."
  sleep 1
done

python manage.py check --database default --fail-level ERROR || true

echo "[start] Running migrations..."
python manage.py migrate --noinput

if [[ "${DJANGO_COLLECTSTATIC:-0}" == "1" ]]; then
  echo "[start] Collecting static..."
  python manage.py collectstatic --noinput
else
  echo "[start] Skipping collectstatic (set DJANGO_COLLECTSTATIC=1 to enable)"
fi

if [[ "${DJANGO_CREATE_SUPERUSER:-0}" == "1" ]]; then
  echo "[start] Recreating superuser..."
  python manage.py shell -c "
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
email    = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin*^%$#@*')
first    = os.environ.get('DJANGO_SUPERUSER_FIRST_NAME', 'Admin')
last     = os.environ.get('DJANGO_SUPERUSER_LAST_NAME', 'User')

existing = User.objects.filter(username=username)

if existing.exists():
    existing.delete()
    print(f'deleted existing superuser: {username}')

User.objects.create_superuser(
    username=username,
    email=email,
    password=password,
    first_name=first,
    last_name=last,
)
print(f'created superuser: {username}')
"
else
  echo "[start] Skipping superuser creation (set DJANGO_CREATE_SUPERUSER=1 to enable)"
fi

echo "[start] Starting gunicorn..."

: "${ENV_TYPE:=local}"
: "${PORT:=8000}"
: "${GUNICORN_WORKERS:=3}"
: "${GUNICORN_TIMEOUT:=60}"
: "${GUNICORN_LOG_LEVEL:=info}"

APP_DIR="/session_auth"
BIND="0.0.0.0:${PORT}"
WSGI_APP="config.wsgi:application"

if [[ "${ENV_TYPE}" == "prod" ]]; then
  exec gunicorn "${WSGI_APP}" \
    --chdir "${APP_DIR}" \
    --bind "${BIND}" \
    --workers "${GUNICORN_WORKERS}" \
    --timeout "${GUNICORN_TIMEOUT}" \
    --log-level "${GUNICORN_LOG_LEVEL}" \
    --access-logfile "-" \
    --error-logfile "-" \
    --capture-output
else
  exec gunicorn "${WSGI_APP}" \
    --chdir "${APP_DIR}" \
    --bind "${BIND}" \
    --reload \
    --log-level debug \
    --access-logfile "-" \
    --error-logfile "-" \
    --capture-output
fi
echo "== Gunicorn exited ==
