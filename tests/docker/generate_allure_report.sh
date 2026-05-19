#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/workspace"
COMBINED_DIR="${ROOT_DIR}/tests/artifacts/allure-results/combined"
REPORT_DIR="${ROOT_DIR}/tests/artifacts/allure-report"
COVERAGE_DIR="${REPORT_DIR}/coverage"

rm -rf "${COMBINED_DIR}"
mkdir -p "${COMBINED_DIR}" "${REPORT_DIR}"
find "${REPORT_DIR}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +

for source_dir in \
  "${ROOT_DIR}/tests/artifacts/allure-results/smoke_tests" \
  "${ROOT_DIR}/tests/artifacts/allure-results/functional_tests" \
  "${ROOT_DIR}/tests/artifacts/allure-results/component_tests" \
  "${ROOT_DIR}/tests/artifacts/allure-results/integration_tests" \
  "${ROOT_DIR}/tests/artifacts/allure-results/security_tests" \
  "${ROOT_DIR}/tests/artifacts/allure-results/performance_tests" \
  "${ROOT_DIR}/tests/artifacts/allure-results/load_tests" \
  "${ROOT_DIR}/tests/artifacts/allure-results/load_capacity" \
  "${ROOT_DIR}/tests/artifacts/allure-results/dast_tests" \
  "${ROOT_DIR}/stock/tests/artifacts/allure-results" \
  "${ROOT_DIR}/wallet/tests/artifacts/allure-results" \
  "${ROOT_DIR}/session/tests/artifacts/allure-results" \
  "${ROOT_DIR}/next-ui/tests/artifacts/allure-results"
do
  if [ -d "${source_dir}" ]; then
    find "${source_dir}" -maxdepth 1 -type f -exec cp {} "${COMBINED_DIR}/" \;
  fi
done

REPORT_DATE=$(date '+%Y-%m-%d %H:%M %Z')
GIT_COMMIT="${GIT_COMMIT:-unknown}"
GIT_BRANCH="${GIT_BRANCH:-unknown}"
GIT_STATUS="${GIT_STATUS:-unknown}"

DJANGO_VERSION=$(grep -m1 '^Django==' "${ROOT_DIR}/session/requirements/requirements.txt" 2>/dev/null | cut -d= -f3 || echo "unknown")
FASTAPI_VERSION=$(grep -m1 '^fastapi==' "${ROOT_DIR}/wallet/requirements/requirements.txt" 2>/dev/null | cut -d= -f3 || echo "unknown")
NODE_VERSION=$(node --version 2>/dev/null || echo "unknown")

cat > "${COMBINED_DIR}/environment.properties" <<EOF
Environment=local-docker
Python\ version=3.12
Django\ version=${DJANGO_VERSION}
FastAPI\ version=${FASTAPI_VERSION}
Node\ version=${NODE_VERSION}
Git\ branch=${GIT_BRANCH}
Git\ commit=${GIT_COMMIT}
Git\ status=${GIT_STATUS}
Report\ generated=${REPORT_DATE}
Coverage\ overview=http://localhost:5252/coverage/
Coverage\ stock=http://localhost:5252/coverage/stock/
Coverage\ wallet=http://localhost:5252/coverage/wallet/
Coverage\ session=http://localhost:5252/coverage/session/
Coverage\ next-ui=http://localhost:5252/coverage/next-ui/
Login\ capacity\ report=http://localhost:5252/load-capacity/login_capacity_probe.html
EOF

cat > "${COMBINED_DIR}/categories.json" <<'EOF'
[
  {
    "name": "Infrastructure Issues",
    "matchedStatuses": ["broken"],
    "messageRegex": ".*ConnectionError.*|.*TimeoutError.*|.*ConnectTimeout.*|.*BrokenPipeError.*|.*ServiceUnavailable.*|.*httpx.*|.*requests.*"
  },
  {
    "name": "Test Defects",
    "matchedStatuses": ["broken"]
  },
  {
    "name": "Product Defects",
    "matchedStatuses": ["failed"]
  },
  {
    "name": "Skipped – Known Gap",
    "matchedStatuses": ["skipped"],
    "messageRegex": ".*flaky.*|.*known.*|.*gap.*"
  }
]
EOF

python "${ROOT_DIR}/tests/docker/generate_npm_audit_result.py" \
  --audit-json "${ROOT_DIR}/next-ui/tests/artifacts/npm-audit.json" \
  --output-dir "${COMBINED_DIR}"

allure generate "${COMBINED_DIR}" --clean -o "${REPORT_DIR}"

mkdir -p "${COVERAGE_DIR}"

if [ -d "${ROOT_DIR}/tests/artifacts/load-capacity" ]; then
  mkdir -p "${REPORT_DIR}/load-capacity"
  cp -R "${ROOT_DIR}/tests/artifacts/load-capacity/." "${REPORT_DIR}/load-capacity/"
fi

for item in \
  "stock:${ROOT_DIR}/stock/tests/artifacts/coverage-html" \
  "wallet:${ROOT_DIR}/wallet/tests/artifacts/coverage-html" \
  "session:${ROOT_DIR}/session/tests/artifacts/coverage-html" \
  "next-ui:${ROOT_DIR}/next-ui/tests/artifacts/coverage-html"
do
  service="${item%%:*}"
  source_dir="${item#*:}"
  if [ -d "${source_dir}" ]; then
    mkdir -p "${COVERAGE_DIR}/${service}"
    cp -R "${source_dir}/." "${COVERAGE_DIR}/${service}/"
  fi
done

python "${ROOT_DIR}/tests/docker/generate_coverage_overview.py" \
  --root "${ROOT_DIR}" \
  --coverage-dir "${COVERAGE_DIR}" \
  --changed-lines "/tmp/coverage-changed-lines.json"
