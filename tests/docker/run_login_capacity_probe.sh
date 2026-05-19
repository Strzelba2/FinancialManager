#!/usr/bin/env bash
set -euo pipefail

RESULTS_DIR="/workspace/tests/artifacts/allure-results/load_capacity"

rm -rf "${RESULTS_DIR}" /workspace/tests/artifacts/load-capacity
mkdir -p "${RESULTS_DIR}"

python -m pytest \
  -c /workspace/tests/pytest.ini \
  /workspace/tests/load_tests/test_login_capacity_probe.py \
  --alluredir "${RESULTS_DIR}"
