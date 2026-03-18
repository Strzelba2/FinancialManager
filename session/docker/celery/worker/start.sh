#!/bin/bash

set -o errexit
set -o nounset

set -euo pipefail

: "${ENV_TYPE:=local}"
: "${CELERY_LOG_LEVEL:=INFO}"
: "${CELERY_CONCURRENCY:=2}"
: "${CELERY_POOL:=prefork}"  

APP="config.celery_session"

if [[ "${ENV_TYPE}" == "prod" ]]; then
  exec celery -A "${APP}" worker \
    -l "${CELERY_LOG_LEVEL}" \
    --concurrency "${CELERY_CONCURRENCY}" \
    --pool "${CELERY_POOL}" \
    --without-gossip --without-mingle
else
  exec watchfiles --filter python \
    "celery.__main__.main" \
    --args "-A ${APP} worker -l ${CELERY_LOG_LEVEL}"
fi