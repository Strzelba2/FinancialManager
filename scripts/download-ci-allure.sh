#!/usr/bin/env bash
set -euo pipefail

WORKFLOW="${WORKFLOW:-Quality}"
BRANCH="${BRANCH:-main}"
ARTIFACT_NAME="${ARTIFACT_NAME:-allure-evidence}"
TARGET_DIR="${TARGET_DIR:-tests/artifacts/ci-allure}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-5252}"
RUN_ID="${RUN_ID:-${1:-}}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI is required. Install gh and run: gh auth login"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to serve the downloaded Allure report."
  exit 1
fi

case "${TARGET_DIR}" in
  "" | "." | "/" )
    echo "Refusing to use unsafe TARGET_DIR='${TARGET_DIR}'."
    exit 1
    ;;
esac

if [ -z "${RUN_ID}" ]; then
  RUN_ID="$(
    gh run list \
      --workflow "${WORKFLOW}" \
      --branch "${BRANCH}" \
      --status completed \
      --limit 1 \
      --json databaseId \
      --jq '.[0].databaseId // ""'
  )"
fi

if [ -z "${RUN_ID}" ]; then
  echo "No completed '${WORKFLOW}' workflow run found on branch '${BRANCH}'."
  exit 1
fi

TMP_DIR="${TARGET_DIR}.tmp"
rm -rf "${TMP_DIR}"
mkdir -p "${TMP_DIR}"

echo "Downloading artifact '${ARTIFACT_NAME}' from workflow run ${RUN_ID}..."
gh run download "${RUN_ID}" --name "${ARTIFACT_NAME}" --dir "${TMP_DIR}"

REPORT_DIR="${TMP_DIR}/tests/artifacts/allure-report"
if [ ! -f "${REPORT_DIR}/index.html" ]; then
  REPORT_INDEX="$(find "${TMP_DIR}" -path "*/allure-report/index.html" -print -quit)"
  if [ -z "${REPORT_INDEX}" ]; then
    echo "Downloaded artifact does not contain a generated Allure HTML report."
    echo "Look inside: ${TMP_DIR}"
    exit 1
  fi
  REPORT_DIR="$(dirname "${REPORT_INDEX}")"
fi

RELATIVE_REPORT_DIR="${REPORT_DIR#${TMP_DIR}/}"
rm -rf "${TARGET_DIR}"
mv "${TMP_DIR}" "${TARGET_DIR}"
REPORT_DIR="${TARGET_DIR}/${RELATIVE_REPORT_DIR}"

echo "Allure report downloaded to: ${REPORT_DIR}"
echo "Serving report at: http://${HOST}:${PORT}"
echo "Press Ctrl+C to stop."

python3 -m http.server "${PORT}" --bind "${HOST}" --directory "${REPORT_DIR}"
