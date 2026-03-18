#!/bin/sh
set -eu

SERVER_JSON="${PGADMIN_SERVER_JSON_FILE:-/var/lib/pgadmin/servers.json}"
PGPASS_PATH="${PGPASS_FILE:-/var/lib/pgadmin/pgpass}"

mkdir -p /var/lib/pgadmin

cat > "${SERVER_JSON}" <<EOF
{
  "Servers": {
    "1": {
      "Name": "financial-manager",
      "Group": "FinancialManager",
      "Host": "${RDS_HOST}",
      "Port": ${RDS_PORT:-5432},
      "MaintenanceDB": "postgres",
      "Username": "${RDS_USER}",
      "SSLMode": "prefer",
      "PassFile": "${PGPASS_PATH}",
      "SavePassword": true
    }
  }
}
EOF

cat > "${PGPASS_PATH}" <<EOF
${RDS_HOST}:${RDS_PORT:-5432}:*:${RDS_USER}:${RDS_PASSWORD}
EOF

chmod 600 "${PGPASS_PATH}"

export PGADMIN_SERVER_JSON_FILE="${SERVER_JSON}"
export PGADMIN_REPLACE_SERVERS_ON_STARTUP="True"
export PGPASS_FILE="${PGPASS_PATH}"

exec /entrypoint.sh