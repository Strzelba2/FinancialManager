#!/usr/bin/env bash
set -euo pipefail

NETWORK_NAME="${1:-financial_manager}"

if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  printf '[network] Using existing Docker network: %s\n' "${NETWORK_NAME}"
  exit 0
fi

printf '[network] Creating Docker network: %s\n' "${NETWORK_NAME}"
docker network create "${NETWORK_NAME}" >/dev/null
