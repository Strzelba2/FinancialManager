#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

PROJECT_NAME="${TEST_COMPOSE_PROJECT_NAME:-financialmanager_tests}"
DEFAULT_NETWORK_NAME="financialmanager_tests_network"
NETWORK_NAME="${TEST_COMPOSE_NETWORK_NAME:-${PROJECT_NAME}_network}"
ZAP_IMAGE="${ZAP_IMAGE:-ghcr.io/zaproxy/zaproxy:stable}"
ZAP_SPIDER_MINUTES="${ZAP_SPIDER_MINUTES:-2}"
ARTIFACT_DIR="${ROOT_DIR}/tests/artifacts/zap-login-dast"
COMPOSE_FILES=(-f docker-compose.yml -f tests/docker-compose.tests.yml)

cleanup() {
  bash tests/docker/reset_test_runtime.sh
}

ensure_artifact_permissions() {
  env UID="$(id -u)" GID="$(id -g)" docker compose -p "${PROJECT_NAME}" "${COMPOSE_FILES[@]}" run --rm --no-deps --user 0:0 \
    test-runner sh -c "mkdir -p /workspace/tests/artifacts && chown -R $(id -u):$(id -g) /workspace/tests/artifacts"
}

cleanup
trap cleanup EXIT

ensure_artifact_permissions
rm -rf "${ARTIFACT_DIR}"
mkdir -p "${ARTIFACT_DIR}"

echo "[zap-login-dast] Starting isolated test runtime..."
env UID="$(id -u)" GID="$(id -g)" docker compose -p "${PROJECT_NAME}" "${COMPOSE_FILES[@]}" up -d \
  --force-recreate \
  --renew-anon-volumes \
  session-db wallet-db stock-db session-auth wallet stock traefik next-ui

echo "[zap-login-dast] Waiting for routed login page..."
for _ in $(seq 1 60); do
  if env UID="$(id -u)" GID="$(id -g)" docker compose -p "${PROJECT_NAME}" "${COMPOSE_FILES[@]}" exec -T session-auth \
    python -c "import urllib.request; req=urllib.request.Request('http://traefik/login', headers={'Host': 'next.localhost'}); urllib.request.urlopen(req, timeout=3).read()" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

traefik_container="$(env UID="$(id -u)" GID="$(id -g)" docker compose -p "${PROJECT_NAME}" "${COMPOSE_FILES[@]}" ps -q traefik)"
traefik_ip="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${traefik_container}")"

if ! docker image inspect "${ZAP_IMAGE}" >/dev/null 2>&1; then
  echo "[zap-login-dast] Pulling ${ZAP_IMAGE}..."
  docker pull "${ZAP_IMAGE}"
fi

echo "[zap-login-dast] Running OWASP ZAP baseline scan for next-ui login..."
docker run --rm \
  --network "${NETWORK_NAME}" \
  --add-host "next.localhost:${traefik_ip}" \
  -v "${ARTIFACT_DIR}:/zap/wrk:rw" \
  "${ZAP_IMAGE}" \
  zap-baseline.py \
  -t "http://next.localhost/login" \
  -m "${ZAP_SPIDER_MINUTES}" \
  -I \
  -r "zap-login-report.html" \
  -J "zap-login-report.json" \
  -w "zap-login-report.md" \
  -z "-config scanner.threadPerHost=2"

chown -R "$(id -u):$(id -g)" "${ARTIFACT_DIR}" || true
echo "[zap-login-dast] Reports written to ${ARTIFACT_DIR}"
