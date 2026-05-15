#!/usr/bin/env bash
set -euo pipefail

RESULTS_DIR="/workspace/tests/artifacts/allure-results/functional_tests"
OUTPUT_DIR="/workspace/tests/artifacts/robot-output/functional_tests"

rm -rf "${RESULTS_DIR}" "${OUTPUT_DIR}"
mkdir -p "${RESULTS_DIR}" "${OUTPUT_DIR}"

robot \
  --outputdir "${OUTPUT_DIR}" \
  --listener "allure_robotframework;${RESULTS_DIR}" \
  --variable BASE_URL:"${BASE_URL:-http://next.localhost}" \
  --variable HOST_RESOLVER_RULES:"${HOST_RESOLVER_RULES:-MAP next.localhost traefik,MAP wallet.localhost traefik,MAP session-auth.localhost traefik,MAP stock.localhost traefik}" \
  --variable HEADLESS:"${HEADLESS:-True}" \
  /workspace/tests/functional_tests/TestSuites
