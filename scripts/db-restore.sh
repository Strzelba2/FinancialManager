#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${ROOT_DIR}/backups/db"

usage() {
  cat <<'EOF'
Usage: bash scripts/db-restore.sh [session|stock|wallet|all] [latest|FILE|DIR]

Examples:
  bash scripts/db-restore.sh session latest
  bash scripts/db-restore.sh stock latest
  bash scripts/db-restore.sh wallet backups/db/20260428_201500/wallet.sql.gz
  bash scripts/db-restore.sh all backups/db/20260428_201500
EOF
}

log() {
  printf '[db-restore] %s\n' "$*"
}

compose() {
  env UID="$(id -u)" GID="$(id -g)" docker compose -f "${ROOT_DIR}/docker-compose.yml" "$@"
}

ensure_network() {
  bash "${ROOT_DIR}/scripts/ensure-docker-network.sh" financial_manager >/dev/null
}

container_env_var() {
  local service="$1"
  local var_name="$2"
  local required="${3:-required}"
  local value

  value="$(compose exec -T "${service}" sh -lc "printenv ${var_name} || true" | tr -d '\r')"
  if [[ -z "${value}" && "${required}" == "required" ]]; then
    log "Missing required variable ${var_name} in container ${service}"
    exit 1
  fi

  printf '%s\n' "${value}"
}

latest_backup_dir() {
  local latest_dir

  if [[ ! -d "${BACKUP_ROOT}" ]]; then
    log "No backups found under ${BACKUP_ROOT#${ROOT_DIR}/}"
    exit 1
  fi

  latest_dir="$(find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
  if [[ -z "${latest_dir}" ]]; then
    log "No backups found under ${BACKUP_ROOT#${ROOT_DIR}/}"
    exit 1
  fi

  printf '%s\n' "${latest_dir}"
}

resolve_backup_file() {
  local name="$1"
  local selector="$2"
  local resolved_selector="${selector}"

  if [[ "${resolved_selector}" == "latest" ]]; then
    resolved_selector="$(latest_backup_dir)"
  fi

  if [[ -d "${resolved_selector}" ]]; then
    printf '%s/%s.sql.gz\n' "${resolved_selector}" "${name}"
  else
    printf '%s\n' "${resolved_selector}"
  fi
}

app_services_for() {
  case "$1" in
    session)
      printf '%s\n' "session-auth celeryworker celerybeat"
      ;;
    stock)
      printf '%s\n' "stock celerystockworker celerystockbeat"
      ;;
    wallet)
      printf '%s\n' "wallet"
      ;;
    *)
      printf '\n'
      ;;
  esac
}

array_contains() {
  local needle="$1"
  shift
  local item

  for item in "$@"; do
    if [[ "${item}" == "${needle}" ]]; then
      return 0
    fi
  done

  return 1
}

restore_service() {
  local name="$1"
  local db_service="$2"
  local selector="$3"
  local dump_file
  local app_services_raw
  local -a app_services=()
  local -a running_services=()
  local -a app_services_to_restart=()
  local service_name
  local pg_user
  local pg_db
  local pg_password

  dump_file="$(resolve_backup_file "${name}" "${selector}")"
  if [[ ! -f "${dump_file}" ]]; then
    log "Backup file not found: ${dump_file}"
    exit 1
  fi

  app_services_raw="$(app_services_for "${name}")"
  if [[ -n "${app_services_raw}" ]]; then
    read -r -a app_services <<< "${app_services_raw}"
  fi

  mapfile -t running_services < <(compose ps --status running --services 2>/dev/null || true)
  for service_name in "${app_services[@]}"; do
    if array_contains "${service_name}" "${running_services[@]}"; then
      app_services_to_restart+=("${service_name}")
    fi
  done

  log "Starting ${db_service} if needed"
  compose up -d "${db_service}" >/dev/null

  pg_user="$(container_env_var "${db_service}" POSTGRES_USER)"
  pg_db="$(container_env_var "${db_service}" POSTGRES_DB)"
  pg_password="$(container_env_var "${db_service}" POSTGRES_PASSWORD optional)"

  (
    trap 'if ((${#app_services_to_restart[@]})); then compose up -d "${app_services_to_restart[@]}" >/dev/null || true; fi' EXIT

    if ((${#app_services_to_restart[@]})); then
      log "Stopping services that use ${name} DB: ${app_services_to_restart[*]}"
      compose stop "${app_services_to_restart[@]}" >/dev/null || true
    fi

    log "Restoring ${name} from ${dump_file#${ROOT_DIR}/}"
    gunzip -c "${dump_file}" | compose exec -T -e "PGPASSWORD=${pg_password}" "${db_service}" \
      psql \
        -v ON_ERROR_STOP=1 \
        -U "${pg_user}" \
        -d "${pg_db}"

    log "Restore finished for ${name}"
  )
}

TARGET="${1:-}"
SELECTOR="${2:-latest}"

case "${TARGET}" in
  session|stock|wallet|all)
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage
    exit 1
    ;;
esac

ensure_network

if [[ "${TARGET}" == "all" && "${SELECTOR}" != "latest" && ! -d "${SELECTOR}" ]]; then
  log "When restoring all databases, provide a backup directory or use 'latest'."
  exit 1
fi

if [[ "${TARGET}" == "session" || "${TARGET}" == "all" ]]; then
  restore_service "session" "session-db" "${SELECTOR}"
fi

if [[ "${TARGET}" == "stock" || "${TARGET}" == "all" ]]; then
  restore_service "stock" "stock-db" "${SELECTOR}"
fi

if [[ "${TARGET}" == "wallet" || "${TARGET}" == "all" ]]; then
  restore_service "wallet" "wallet-db" "${SELECTOR}"
fi
