#!/usr/bin/env bash
set -euo pipefail

LIVE_DB_NAME="${1:-${LIVE_DB_NAME:-}}"
DB_USER="${POSTGRES_USER:-odoo}"
CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
OUTPUT_DIR="${OUTPUT_DIR:-secure_backups}"
INSTALL_MODULES="${INSTALL_MODULES:-elsx_client_restrictions,elsx_attendance_tracking,elsx_face_attendance}"
UPGRADE_MODULES="${UPGRADE_MODULES:-elsx_client_restrictions,elsx_attendance_tracking,elsx_face_attendance}"
EXTRA_INSTALL_MODULES="${EXTRA_INSTALL_MODULES:-}"
EXTRA_UPGRADE_MODULES="${EXTRA_UPGRADE_MODULES:-}"
DEACTIVATE_SAAS_ON_UPDATE="${DEACTIVATE_SAAS_ON_UPDATE:-YES}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

wait_for_db() {
  local attempt
  echo "==> Waiting for PostgreSQL to accept connections"
  for attempt in $(seq 1 60); do
    if docker compose exec -T db pg_isready -U "${DB_USER}" -d postgres >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "ERROR: PostgreSQL did not become ready after 120 seconds." >&2
  docker compose ps db >&2 || true
  exit 1
}

if [ -z "${LIVE_DB_NAME}" ]; then
  echo "ERROR: database name is required. This script will not guess a production database." >&2
  echo "Usage: BACKUP_PASSPHRASE=... bash deploy/safe_production_update.sh <database_name>" >&2
  echo "Example: read -s -p 'Backup passphrase: ' BACKUP_PASSPHRASE && echo && export BACKUP_PASSPHRASE && bash deploy/safe_production_update.sh FiberaFRP_DB" >&2
  exit 2
fi

sql_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "${value}"
}

SAFE_DB_NAME="$(printf '%s' "${LIVE_DB_NAME}" | tr -c 'A-Za-z0-9_.-' '_')"
if [[ "${OUTPUT_DIR}" != /* ]]; then
  OUTPUT_DIR="${PROJECT_DIR}/${OUTPUT_DIR}"
fi
mkdir -p "${OUTPUT_DIR}"

echo "==> Production-safe update for database: ${LIVE_DB_NAME}"
ALL_INSTALL_MODULES="${INSTALL_MODULES}"
if [ -n "${EXTRA_INSTALL_MODULES}" ]; then
  ALL_INSTALL_MODULES="${ALL_INSTALL_MODULES},${EXTRA_INSTALL_MODULES}"
fi

ALL_UPGRADE_MODULES="${UPGRADE_MODULES}"
if [ -n "${EXTRA_UPGRADE_MODULES}" ]; then
  ALL_UPGRADE_MODULES="${ALL_UPGRADE_MODULES},${EXTRA_UPGRADE_MODULES}"
fi

echo "==> Install modules if missing: ${ALL_INSTALL_MODULES}"
echo "==> Upgrade modules: ${ALL_UPGRADE_MODULES}"
echo "==> Deactivate SaaS runtime after update: ${DEACTIVATE_SAAS_ON_UPDATE}"

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  echo "ERROR: BACKUP_PASSPHRASE is required. Refusing to upgrade without an encrypted backup." >&2
  echo "Example: read -s -p 'Backup passphrase: ' BACKUP_PASSPHRASE && echo && export BACKUP_PASSPHRASE && bash deploy/safe_production_update.sh ${LIVE_DB_NAME}" >&2
  exit 1
fi

if [ "${ALLOW_DIRTY_CODE:-NO}" != "YES" ]; then
  if [ -n "$(git status --short --untracked-files=no)" ]; then
    echo "ERROR: tracked Git files are modified. Commit/stash or rerun with ALLOW_DIRTY_CODE=YES after review." >&2
    git status --short --untracked-files=no >&2
    exit 1
  fi
fi

echo "==> Ensuring PostgreSQL is running"
docker compose up -d db
wait_for_db

if ! DB_EXISTS="$(
  docker compose exec -T db psql -U "${DB_USER}" -d postgres -Atc \
    "SELECT 1 FROM pg_database WHERE datname = $(sql_quote "${LIVE_DB_NAME}");"
)"; then
  echo "ERROR: failed to check database ${LIVE_DB_NAME}. Refusing to continue." >&2
  exit 1
fi
if [ "${DB_EXISTS}" != "1" ]; then
  echo "ERROR: Database ${LIVE_DB_NAME} does not exist." >&2
  exit 1
fi

echo "==> Creating encrypted backup before any module upgrade"
OUTPUT_DIR="${OUTPUT_DIR}" BACKUP_PASSPHRASE="${BACKUP_PASSPHRASE}" \
  bash deploy/export_live_encrypted_backup.sh "${LIVE_DB_NAME}"

LATEST_BACKUP="$(ls -t "${OUTPUT_DIR}/${SAFE_DB_NAME}"*_portable.tar.gz.enc 2>/dev/null | head -n 1 || true)"
if [ -z "${LATEST_BACKUP}" ] || [ ! -s "${LATEST_BACKUP}" ]; then
  echo "ERROR: encrypted backup was not created or is empty. Refusing to continue." >&2
  exit 1
fi
echo "==> Verified encrypted backup: ${LATEST_BACKUP}"

echo "==> Building Odoo image"
docker compose build odoo

echo "==> Stopping Odoo and WhatsApp sidecar for a clean module upgrade"
docker compose stop sidecar >/dev/null 2>&1 || true
docker compose stop odoo >/dev/null 2>&1 || true

echo "==> Installing/upgrading requested modules through the backup-protected path"
docker compose run --rm -T --no-deps odoo \
  python3 /opt/odoo/odoo-bin \
    -c "${CONFIG}" \
    -d "${LIVE_DB_NAME}" \
    -i "${ALL_INSTALL_MODULES}" \
    -u "${ALL_UPGRADE_MODULES}" \
    --stop-after-init

if [ "${DEACTIVATE_SAAS_ON_UPDATE}" = "YES" ]; then
  echo "==> Deactivating SaaS runtime metadata for ${LIVE_DB_NAME} (no uninstall, no data deletion)"
  CONFIRM_DEACTIVATE_SAAS=YES TARGET_DBS="${LIVE_DB_NAME}" bash deploy/deactivate_saas_all_dbs.sh
fi
echo "==> Starting Odoo and WhatsApp sidecar"
docker compose up -d odoo sidecar

echo "==> Module state check"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT name, state, latest_version
     FROM ir_module_module
    WHERE name IN ('elsx_client_restrictions','elsx_attendance_tracking','elsx_face_attendance','elsx_saas','elsx_whatsapp_marketing','elsx_tally_integration','crm','account','hr_attendance')
    ORDER BY name;"

echo "==> Container status"
docker compose ps

echo
echo "==> Safe production update complete."
echo "Backup kept at: ${LATEST_BACKUP}"
echo "Face sidecar remains disabled unless explicitly started with:"
echo "    docker compose --profile face up -d face_sidecar"
echo "Check logs with:"
echo "    docker logs --tail 250 odoo_app"
