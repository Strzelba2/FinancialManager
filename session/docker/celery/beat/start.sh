#!/usr/bin/env bash
set -euo pipefail

: "${ENV_TYPE:=local}"

PIDFILE="${CELERY_BEAT_PIDFILE:-/tmp/celerybeat.pid}"
rm -f "${PIDFILE}"

APP="config.celery_session"

if [[ "${ENV_TYPE}" == "prod" ]]; then
  exec celery -A "${APP}" beat \
    -l INFO \
    --pidfile="${PIDFILE}"
else
  exec watchfiles --filter python \
    "celery.__main__.main" \
    --args "-A ${APP} beat -l INFO --pidfile=${PIDFILE}"
fi