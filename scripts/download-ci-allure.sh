#!/usr/bin/env bash
set -euo pipefail

WORKFLOW="${WORKFLOW:-Quality}"
BRANCH="${BRANCH:-main}"
ARTIFACT_NAME="${ARTIFACT_NAME:-allure-evidence}"
TARGET_DIR="${TARGET_DIR:-${TMPDIR:-/tmp}/financialmanager-ci-allure}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-5252}"
RUN_ID="${RUN_ID:-${1:-}}"
REPO="${GITHUB_REPOSITORY:-${REPO:-}}"
SERVE="${SERVE:-1}"
ACCESS_TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
PROMPT_FOR_TOKEN="${PROMPT_FOR_TOKEN:-1}"

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

resolve_repo() {
  if [ -n "${REPO}" ]; then
    echo "${REPO}"
    return
  fi

  local origin
  origin="$(git config --get remote.origin.url 2>/dev/null || true)"
  python3 - "${origin}" <<'PY'
import re
import sys

origin = sys.argv[1]
patterns = (
    r"github\.com[:/](?P<repo>[^/]+/[^/.]+)(?:\.git)?$",
    r"github\.com/(?P<repo>[^/]+/[^/.]+)(?:\.git)?$",
)
for pattern in patterns:
    match = re.search(pattern, origin)
    if match:
        print(match.group("repo"))
        raise SystemExit(0)
raise SystemExit(1)
PY
}

json_get() {
  python3 -c '
import json
import sys

data = json.load(sys.stdin)
path = sys.argv[1].split(".") if sys.argv[1] else []
default = sys.argv[2]
value = data
try:
    for part in path:
        if part.endswith("]"):
            name, index = part[:-1].split("[")
            value = value[name][int(index)]
        else:
            value = value[part]
except (KeyError, IndexError, TypeError, ValueError):
    value = default
print(value if value is not None else default)
' "$1" "$2"
}

find_workflow_id() {
  python3 -c '
import json
import sys

workflow_ref = sys.argv[1]
data = json.load(sys.stdin)
for workflow in data.get("workflows", []):
    workflow_id = str(workflow.get("id", ""))
    name = workflow.get("name", "")
    path = workflow.get("path", "")
    if workflow_ref in {workflow_id, name, path} or path.endswith(f"/{workflow_ref}"):
        print(workflow_id)
        raise SystemExit(0)
raise SystemExit(1)
' "${WORKFLOW}"
}

find_artifact_url() {
  python3 -c '
import json
import sys

artifact_name = sys.argv[1]
data = json.load(sys.stdin)
for artifact in data.get("artifacts", []):
    if artifact.get("name") == artifact_name:
        print(artifact.get("archive_download_url", ""))
        raise SystemExit(0)
raise SystemExit(1)
' "${ARTIFACT_NAME}"
}

prompt_for_token() {
  if [ -n "${ACCESS_TOKEN}" ] || [ "${PROMPT_FOR_TOKEN}" = "0" ]; then
    return
  fi

  if [ -t 0 ]; then
    echo "GitHub may require authentication to download Actions artifacts."
    printf "Paste GitHub token for this run only (hidden, Enter to try without token): " >&2
    IFS= read -r -s ACCESS_TOKEN || true
    printf "\n" >&2
  fi
}

download_with_gh() {
  if ! command -v gh >/dev/null 2>&1; then
    return 1
  fi

  if [ -z "${RUN_ID}" ]; then
    if ! RUN_ID="$(
      gh run list \
        --workflow "${WORKFLOW}" \
        --branch "${BRANCH}" \
        --status completed \
        --limit 1 \
        --json databaseId \
        --jq '.[0].databaseId // ""'
    )"; then
      return 1
    fi
  fi

  if [ -z "${RUN_ID}" ]; then
    echo "No completed '${WORKFLOW}' workflow run found on branch '${BRANCH}'."
    exit 1
  fi

  echo "Downloading artifact '${ARTIFACT_NAME}' from workflow run ${RUN_ID} with gh..."
  gh run download "${RUN_ID}" --name "${ARTIFACT_NAME}" --dir "${TMP_DIR}" || return 1
}

download_with_api() {
  if ! command -v curl >/dev/null 2>&1; then
    echo "GitHub CLI is not installed and curl is not available."
    echo "Install gh and run 'gh auth login', or install curl and optionally export GITHUB_TOKEN."
    exit 1
  fi

  if ! command -v unzip >/dev/null 2>&1; then
    echo "GitHub CLI is not installed and unzip is not available."
    echo "Install gh and run 'gh auth login', or install unzip for the GitHub API fallback."
    exit 1
  fi

  local repo
  if ! repo="$(resolve_repo)"; then
    echo "Could not detect GitHub repository from remote.origin.url."
    echo "Set REPO=owner/name, for example: REPO=Strzelba2/FinancialManager make ci-allure-up"
    exit 1
  fi

  prompt_for_token

  local auth_args=()
  if [ -n "${ACCESS_TOKEN}" ]; then
    auth_args=(-H "Authorization: Bearer ${ACCESS_TOKEN}")
  fi

  local api="https://api.github.com/repos/${repo}"
  local workflows_json workflow_id runs_json branch_query artifacts_json artifact_url zip_path

  workflows_json="$(curl -fsSL "${auth_args[@]}" -H "Accept: application/vnd.github+json" "${api}/actions/workflows")"
  if ! workflow_id="$(printf "%s" "${workflows_json}" | find_workflow_id)"; then
    echo "Workflow '${WORKFLOW}' was not found in ${repo}."
    exit 1
  fi

  if [ -z "${RUN_ID}" ]; then
    branch_query="$(python3 - "${BRANCH}" <<'PY'
from urllib.parse import quote
import sys
print(quote(sys.argv[1], safe=""))
PY
)"
    runs_json="$(curl -fsSL "${auth_args[@]}" -H "Accept: application/vnd.github+json" "${api}/actions/workflows/${workflow_id}/runs?branch=${branch_query}&status=completed&per_page=1")"
    RUN_ID="$(printf "%s" "${runs_json}" | json_get "workflow_runs[0].id" "")"
  fi

  if [ -z "${RUN_ID}" ]; then
    echo "No completed '${WORKFLOW}' workflow run found on branch '${BRANCH}'."
    exit 1
  fi

  artifacts_json="$(curl -fsSL "${auth_args[@]}" -H "Accept: application/vnd.github+json" "${api}/actions/runs/${RUN_ID}/artifacts?per_page=100")"
  if ! artifact_url="$(printf "%s" "${artifacts_json}" | find_artifact_url)"; then
    echo "Artifact '${ARTIFACT_NAME}' was not found in workflow run ${RUN_ID}."
    exit 1
  fi

  zip_path="${TARGET_DIR}.zip.tmp"
  rm -f "${zip_path}"
  echo "Downloading artifact '${ARTIFACT_NAME}' from workflow run ${RUN_ID} with GitHub API..."
  if ! curl -fL "${auth_args[@]}" -H "Accept: application/vnd.github+json" "${artifact_url}" -o "${zip_path}"; then
    echo "Could not download the artifact archive from GitHub."
    echo "If GitHub requires authentication, install gh and run 'gh auth login',"
    echo "or export GITHUB_TOKEN/GH_TOKEN with read access to Actions artifacts."
    rm -f "${zip_path}"
    exit 1
  fi

  unzip -q "${zip_path}" -d "${TMP_DIR}"
  rm -f "${zip_path}"
}


TMP_DIR="${TARGET_DIR}.tmp"
rm -rf "${TMP_DIR}"
mkdir -p "${TMP_DIR}"

if ! download_with_gh; then
  download_with_api
fi

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

if [ "${SERVE}" = "0" ]; then
  exit 0
fi

echo "Serving report at: http://${HOST}:${PORT}"
echo "Press Ctrl+C to stop."

python3 -m http.server "${PORT}" --bind "${HOST}" --directory "${REPORT_DIR}"
