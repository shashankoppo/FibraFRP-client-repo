#!/usr/bin/env bash
set -euo pipefail

MASTER_DB_NAME="${1:-${SAAS_MASTER_DB:-EVO_DB}}"
DB_USER="${POSTGRES_USER:-odoo}"
CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
MASTER_MODULES="${SAAS_MASTER_MODULES:-base,elsx_client_restrictions}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

wait_for_db() {
  local attempt
  echo "==> Waiting for PostgreSQL"
  for attempt in $(seq 1 60); do
    if docker compose exec -T db pg_isready -U "${DB_USER}" -d postgres >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "ERROR: PostgreSQL did not become ready." >&2
  exit 1
}

if [[ ! "${MASTER_DB_NAME}" =~ ^[A-Za-z0-9_.-]+$ ]]; then
  echo "ERROR: unsafe SaaS master database name: ${MASTER_DB_NAME}" >&2
  exit 2
fi

if [ "${MASTER_DB_NAME}" = "FiberaFRP_DB" ] || [ "${MASTER_DB_NAME}" = "qwerty" ]; then
  echo "ERROR: refusing to use client database '${MASTER_DB_NAME}' as SaaS master." >&2
  echo "Use a separate master database such as EVO_DB." >&2
  exit 2
fi

echo "==> SaaS master bootstrap target: ${MASTER_DB_NAME}"
echo "==> This script creates the master DB only if it does not exist. It does not touch tenant/client databases."

docker compose up -d db
wait_for_db

DB_EXISTS="$(docker compose exec -T db psql -U "${DB_USER}" -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='${MASTER_DB_NAME}'" || true)"
if [ "${DB_EXISTS}" = "1" ]; then
  echo "==> ${MASTER_DB_NAME} already exists. Skipping creation."
  echo "==> To upgrade the existing SaaS master later, run:"
  echo "    TARGET_DBS=${MASTER_DB_NAME} CONFIRM_TARGET_DBS=YES BACKUP_PASSPHRASE=... bash deploy/safe_update_all_dbs.sh"
  exit 0
fi

echo "==> Creating ${MASTER_DB_NAME} with safe admin modules: ${MASTER_MODULES}"
docker compose run --rm odoo python3 /opt/odoo/odoo-bin \
  -c "${CONFIG}" \
  -d "${MASTER_DB_NAME}" \
  -i "${MASTER_MODULES}" \
  --without-demo=all \
  --stop-after-init

echo "==> Starting application services"
docker compose up -d odoo sidecar

echo "==> Done. Open /web?db=${MASTER_DB_NAME}. SaaS governance remains disabled unless SAAS_MASTER_MODULES explicitly includes elsx_saas in a separate approved rollout."
