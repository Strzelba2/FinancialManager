#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

cd /session_auth

echo "[start] user=$(id -u):$(id -g)"
echo "[start] pwd=$(pwd)"

echo "[start] Waiting for database..."

export POSTGRES_HOST="${POSTGRES_HOST:-session-db}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"

until python - <<'PY'
import os
import psycopg2

psycopg2.connect(
    dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host=os.environ.get("POSTGRES_HOST", "session-db"),
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
  echo "[start] Ensuring superuser exists..."
  python manage.py shell -c "
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
email    = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin*^%$#@*')
first    = os.environ.get('DJANGO_SUPERUSER_FIRST_NAME', 'Admin')
last     = os.environ.get('DJANGO_SUPERUSER_LAST_NAME', 'User')

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(
        username=username,
        email=email,
        password=password,
        first_name=first,
        last_name=last,
    )
    print(f'created superuser: {username}')
else:
    print(f'superuser exists: {username}')
"
else
  echo "[start] Skipping superuser creation (set DJANGO_CREATE_SUPERUSER=1 to enable)"
fi

echo "[start] Starting gunicorn..."

exec gunicorn config.wsgi --bind 0.0.0.0:8000 --chdir=/session_auth --reload

echo "== Gunicorn exited ==
