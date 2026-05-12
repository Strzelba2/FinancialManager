#!/usr/bin/env bash
set -euo pipefail

GROUP_NAME="${1:?Pass a tests group such as component_tests or integration_tests.}"
RESULTS_DIR="/workspace/tests/artifacts/allure-results/${GROUP_NAME}"

rm -rf "${RESULTS_DIR}"
mkdir -p "${RESULTS_DIR}"

python -m pytest \
  -c /workspace/tests/pytest.ini \
  "/workspace/tests/${GROUP_NAME}" \
  --alluredir "${RESULTS_DIR}"
