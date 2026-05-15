#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <command> [args...]" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

PROJECT_NAME="${TEST_COMPOSE_PROJECT_NAME:-financialmanager_tests}"
export TEST_COMPOSE_PROJECT_NAME="${PROJECT_NAME}"
COMPOSE_FILES=(-f docker-compose.yml -f tests/docker-compose.tests.yml)

cleanup() {
  bash tests/docker/reset_test_runtime.sh
}

cleanup
trap cleanup EXIT

echo "[test-runtime] Starting session, wallet, and stock against fresh test databases..."
env UID="$(id -u)" GID="$(id -g)" docker compose -p "${PROJECT_NAME}" "${COMPOSE_FILES[@]}" up -d \
  --force-recreate \
  --renew-anon-volumes \
  session-db wallet-db stock-db session-auth wallet stock

env UID="$(id -u)" GID="$(id -g)" docker compose -p "${PROJECT_NAME}" "${COMPOSE_FILES[@]}" run --rm test-runner "$@"
