#!/usr/bin/env bash
set -euo pipefail

: "${ENV_TYPE:=local}"

: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:=}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

: "${APP_HOST:=0.0.0.0}"
: "${APP_PORT:=8001}"

: "${UVICORN_WORKERS:=2}"
: "${UVICORN_LOG_LEVEL:=info}"
: "${UVICORN_PROXY_HEADERS:=true}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  if [[ -z "${POSTGRES_PASSWORD}" ]]; then
    echo "[start] WARNING: POSTGRES_PASSWORD is empty; building DATABASE_URL without password."
    export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
  else
    export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
  fi
  echo "[start] DATABASE_URL constructed from POSTGRES_* (host=${POSTGRES_HOST}, db=${POSTGRES_DB})"
else
  echo "[start] DATABASE_URL provided externally (host=${POSTGRES_HOST}, db=${POSTGRES_DB})"
fi

echo "[start] Waiting for Postgres at ${POSTGRES_HOST}:${POSTGRES_PORT} (db=${POSTGRES_DB})..."

ready=0

for i in {1..60}; do
  if python - <<'PY' >/dev/null 2>&1
import os, asyncio, asyncpg

async def main():
    conn = await asyncpg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        user=os.environ["POSTGRES_USER"],
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        database=os.environ["POSTGRES_DB"],
        timeout=2,
    )
    await conn.close()

asyncio.run(main())
PY
  then
    ready=1
    break
  fi
  sleep 1
done

if [[ "${ready}" != "1" ]]; then
  echo "[start] ERROR: Postgres not reachable after waiting."
  exit 1
fi

echo "[start] Running Alembic migrations..."
alembic upgrade head

echo "[start] Starting app (ENV_TYPE=${ENV_TYPE})..."

if [[ "${ENV_TYPE}" == "prod" ]]; then
  exec uvicorn app.main:app \
    --host "${APP_HOST}" \
    --port "${APP_PORT}" \
    --workers "${UVICORN_WORKERS}" \
    --log-level "${UVICORN_LOG_LEVEL}" \
    $( [[ "${UVICORN_PROXY_HEADERS}" == "true" ]] && echo "--proxy-headers" )
else
  exec uvicorn app.main:app \
    --host "${APP_HOST}" \
    --port "${APP_PORT}" \
    --reload \
    --log-level debug
fi