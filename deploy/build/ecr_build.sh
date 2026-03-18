#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.build.yml"

DO_PUSH="false"
if [[ "${1:-}" == "--push" || "${1:-}" == "push" ]]; then
  DO_PUSH="true"
  shift
fi

: "${TAG:=test}"
: "${ECR_REGISTRY:=local}"

COMPOSE=(docker compose -f "${COMPOSE_FILE}")
SERVICES=("$@")

echo "Using:"
echo "  ECR_REGISTRY=${ECR_REGISTRY}"
echo "  TAG=${TAG}"
echo "  Compose file=${COMPOSE_FILE}"
echo

echo "Building prod targets..."
if (( ${#SERVICES[@]} )); then
  ECR_REGISTRY="${ECR_REGISTRY}" TAG="${TAG}" "${COMPOSE[@]}" build --pull "${SERVICES[@]}"
else
  ECR_REGISTRY="${ECR_REGISTRY}" TAG="${TAG}" "${COMPOSE[@]}" build --pull
fi

if [[ "${DO_PUSH}" == "true" ]]; then
  echo
  echo "Pushing images..."
  if (( ${#SERVICES[@]} )); then
    ECR_REGISTRY="${ECR_REGISTRY}" TAG="${TAG}" "${COMPOSE[@]}" push "${SERVICES[@]}"
  else
    ECR_REGISTRY="${ECR_REGISTRY}" TAG="${TAG}" "${COMPOSE[@]}" push
  fi
fi

echo
echo "Done."