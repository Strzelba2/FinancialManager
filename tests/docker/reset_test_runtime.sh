#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

PROJECT_NAME="${TEST_COMPOSE_PROJECT_NAME:-financialmanager_tests}"
export TEST_COMPOSE_PROJECT_NAME="${PROJECT_NAME}"
COMPOSE_FILES=(-f docker-compose.yml -f tests/docker-compose.tests.yml)

echo "[test-runtime] Removing test project containers, volumes, and network..."
env UID="$(id -u)" GID="$(id -g)" docker compose -p "${PROJECT_NAME}" "${COMPOSE_FILES[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
