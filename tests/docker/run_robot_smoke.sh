#!/usr/bin/env bash
set -euo pipefail

RESULTS_DIR="/workspace/tests/artifacts/allure-results/smoke_tests"
OUTPUT_DIR="/workspace/tests/artifacts/robot-output/smoke_tests"

rm -rf "${RESULTS_DIR}" "${OUTPUT_DIR}"
mkdir -p "${RESULTS_DIR}" "${OUTPUT_DIR}"

robot \
  --outputdir "${OUTPUT_DIR}" \
  --listener "allure_robotframework;${RESULTS_DIR}" \
  /workspace/tests/smoke_tests/TestSuites
