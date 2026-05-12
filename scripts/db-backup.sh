#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${ROOT_DIR}/backups/db"

usage() {
  cat <<'EOF'
Usage: bash scripts/db-backup.sh [stock|wallet|all]

Examples:
  bash scripts/db-backup.sh all
  bash scripts/db-backup.sh session
  bash scripts/db-backup.sh stock
EOF
}

log() {
  printf '[db-backup] %s\n' "$*"
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

backup_service() {
  local name="$1"
  local db_service="$2"
  local output_file="${RUN_DIR}/${name}.sql.gz"
  local pg_user
  local pg_db
  local pg_password

  log "Starting ${db_service} if needed"
  compose up -d "${db_service}" >/dev/null

  pg_user="$(container_env_var "${db_service}" POSTGRES_USER)"
  pg_db="$(container_env_var "${db_service}" POSTGRES_DB)"
  pg_password="$(container_env_var "${db_service}" POSTGRES_PASSWORD optional)"

  log "Creating backup for ${name} -> ${output_file#${ROOT_DIR}/}"
  compose exec -T -e "PGPASSWORD=${pg_password}" "${db_service}" \
    pg_dump \
      --clean \
      --if-exists \
      --no-owner \
      --no-privileges \
      -U "${pg_user}" \
      -d "${pg_db}" \
    | gzip > "${output_file}"
}

TARGET="${1:-all}"

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

RUN_DIR="${BACKUP_ROOT}/$(date +%Y%m%d_%H%M%S)"
mkdir -p "${RUN_DIR}"
ensure_network

{
  printf 'created_at=%s\n' "$(date -Iseconds)"
  printf 'target=%s\n' "${TARGET}"
} > "${RUN_DIR}/metadata.txt"

if [[ "${TARGET}" == "stock" || "${TARGET}" == "all" ]]; then
  backup_service "stock" "stock-db"
fi

if [[ "${TARGET}" == "session" || "${TARGET}" == "all" ]]; then
  backup_service "session" "session-db"
fi

if [[ "${TARGET}" == "wallet" || "${TARGET}" == "all" ]]; then
  backup_service "wallet" "wallet-db"
fi

log "Backup finished: ${RUN_DIR#${ROOT_DIR}/}"
