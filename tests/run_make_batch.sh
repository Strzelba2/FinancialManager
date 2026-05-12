#!/usr/bin/env bash
set -uo pipefail

MAKE_BIN="${MAKE:-make}"
REPORT_TARGET="${REPORT_TARGET:-}"
OVERALL_STATUS=0

run_target() {
  local target="$1"

  printf '\n===== Running %s =====\n' "${target}"
  if "${MAKE_BIN}" "${target}"; then
    printf '===== Passed %s =====\n' "${target}"
  else
    local exit_code=$?
    OVERALL_STATUS=1
    printf '===== Failed %s (exit %s) =====\n' "${target}" "${exit_code}"
  fi
}

for target in "$@"; do
  run_target "${target}"
done

if [ -n "${REPORT_TARGET}" ]; then
  run_target "${REPORT_TARGET}"
fi

exit "${OVERALL_STATUS}"
