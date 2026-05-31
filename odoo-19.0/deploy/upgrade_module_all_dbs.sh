#!/usr/bin/env bash
set -euo pipefail

MODULE="${1:-elsx_whatsapp_marketing}"
CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
DB_USER="${POSTGRES_USER:-odoo}"
DB_NAME_EXCLUDES="${DB_NAME_EXCLUDES:-postgres}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

echo "==> Ensuring PostgreSQL is running"
docker compose up -d db

echo "==> Stopping Odoo/sidecar during module upgrades"
docker compose stop sidecar >/dev/null 2>&1 || true
docker compose stop odoo >/dev/null 2>&1 || true

EXCLUDE_SQL="'$(echo "${DB_NAME_EXCLUDES}" | sed "s/,/','/g")'"
mapfile -t DATABASES < <(
  docker compose exec -T db psql -U "${DB_USER}" -d postgres -Atc \
    "SELECT datname
       FROM pg_database
      WHERE datistemplate = false
        AND datallowconn = true
        AND datname NOT IN (${EXCLUDE_SQL})
      ORDER BY datname;"
)

if [ "${#DATABASES[@]}" -eq 0 ]; then
  echo "No application databases found. Nothing to upgrade."
  docker compose up -d odoo sidecar
  exit 0
fi

echo "==> Upgrading ${MODULE} in ${#DATABASES[@]} database(s): ${DATABASES[*]}"

for DB in "${DATABASES[@]}"; do
  echo
  echo "---- Upgrading ${MODULE} on database: ${DB}"
  docker compose run --rm -T --no-deps odoo \
    python3 /opt/odoo/odoo-bin \
      -c "${CONFIG}" \
      -d "${DB}" \
      -u "${MODULE}" \
      --stop-after-init
done

echo
echo "==> Starting Odoo and sidecar"
docker compose up -d odoo sidecar

echo "==> Done. Check logs with:"
echo "    docker logs --tail 200 odoo_app"
