#!/bin/bash

set -o errexit

set -o nounset

set -o pipefail

echo "Waiting for Postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
for i in {1..60}; do
  if command -v pg_isready >/dev/null 2>&1; then
    pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" >/dev/null 2>&1 && break
  else
    # fallback: try a TCP connect via python
    python - <<'PY' >/dev/null 2>&1 && break || true
import os, socket
host=os.environ["POSTGRES_HOST"]; port=int(os.environ["POSTGRES_PORT"])
s=socket.socket(); s.settimeout(1.0)
s.connect((host, port)); s.close()
PY
  fi
  sleep 1
done

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting app..."

exec uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload