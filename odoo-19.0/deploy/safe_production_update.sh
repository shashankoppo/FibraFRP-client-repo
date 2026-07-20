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

capture_identity_snapshot() {
  local output_file="$1"
  shift
  local table count checksum

  : > "${output_file}"
  for table in "$@"; do
    if [[ ! "${table}" =~ ^[a-z0-9_]+$ ]]; then
      echo "ERROR: refusing to audit unexpected table name: ${table}" >&2
      exit 1
    fi
    count="$(
      docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -Atc \
        "SELECT count(*) FROM ${table};"
    )"
    checksum="$(
      docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -Atc \
        "COPY (SELECT id FROM ${table} ORDER BY id) TO STDOUT" \
        | sha256sum | awk '{print $1}'
    )"
    printf '%s|%s|%s\n' "${table}" "${count}" "${checksum}" >> "${output_file}"
  done

  count="$(
    docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -Atc \
      "SELECT count(*) FROM ir_attachment WHERE res_model LIKE 'whatsapp.%' OR res_model LIKE 'elsx.ai.%';"
  )"
  checksum="$(
    docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -Atc \
      "COPY (SELECT id FROM ir_attachment WHERE res_model LIKE 'whatsapp.%' OR res_model LIKE 'elsx.ai.%' ORDER BY id) TO STDOUT" \
      | sha256sum | awk '{print $1}'
  )"
  printf '%s|%s|%s\n' 'ir_attachment_whatsapp_ai' "${count}" "${checksum}" >> "${output_file}"
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

echo "==> Building Odoo image before the maintenance window"
docker compose build odoo

echo "==> Stopping Odoo and WhatsApp sidecar for a consistent backup and module upgrade"
docker compose stop sidecar >/dev/null 2>&1 || true
docker compose stop odoo >/dev/null 2>&1 || true

echo "==> Creating encrypted backup before any module upgrade"
OUTPUT_DIR="${OUTPUT_DIR}" BACKUP_PASSPHRASE="${BACKUP_PASSPHRASE}" \
  bash deploy/export_live_encrypted_backup.sh "${LIVE_DB_NAME}"

LATEST_BACKUP="$(ls -t "${OUTPUT_DIR}/${SAFE_DB_NAME}"*_portable.tar.gz.enc 2>/dev/null | head -n 1 || true)"
if [ -z "${LATEST_BACKUP}" ] || [ ! -s "${LATEST_BACKUP}" ]; then
  echo "ERROR: encrypted backup was not created or is empty. Refusing to continue." >&2
  exit 1
fi
echo "==> Verifying encrypted archive integrity and passphrase"
if ! openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -pass env:BACKUP_PASSPHRASE -in "${LATEST_BACKUP}" 2>/dev/null \
  | tar -tzf - >/dev/null; then
  echo "ERROR: encrypted backup could not be decrypted and listed. Refusing to continue." >&2
  exit 1
fi
BACKUP_REFERENCE="$(basename "${LATEST_BACKUP}")"
BACKUP_SHA256="$(sha256sum "${LATEST_BACKUP}" | awk '{print $1}')"
BACKUP_VERIFIED_AT="$(date -u '+%Y-%m-%d %H:%M:%S')"
echo "==> Verified encrypted backup: ${LATEST_BACKUP}"
echo "==> Backup SHA-256: ${BACKUP_SHA256}"

echo "==> Capturing protected business-row identity snapshot"
mapfile -t PROTECTED_TABLES < <(
  docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -Atc \
    "SELECT DISTINCT tables.tablename
       FROM pg_tables AS tables
       JOIN information_schema.columns AS columns
         ON columns.table_schema = tables.schemaname
        AND columns.table_name = tables.tablename
        AND columns.column_name = 'id'
      WHERE tables.schemaname = 'public'
        AND NOT EXISTS (
            SELECT 1
              FROM ir_model AS models
             WHERE replace(models.model, '.', '_') = tables.tablename
               AND models.transient
        )
        AND (
             tables.tablename LIKE 'whatsapp\\_%%' ESCAPE '\\'
          OR tables.tablename LIKE 'elsx_ai\\_%%' ESCAPE '\\'
          OR tables.tablename IN ('res_partner', 'crm_lead', 'sale_order', 'account_move')
        )
      ORDER BY tables.tablename;"
)
IDENTITY_SNAPSHOT_BEFORE="${LATEST_BACKUP}.business-identities.before.sha256"
IDENTITY_SNAPSHOT_AFTER="${LATEST_BACKUP}.business-identities.after.sha256"
capture_identity_snapshot "${IDENTITY_SNAPSHOT_BEFORE}" "${PROTECTED_TABLES[@]}"

echo "==> Installing/upgrading requested modules through the backup-protected path"
docker compose run --rm -T --no-deps odoo \
  python3 /opt/odoo/odoo-bin \
    -c "${CONFIG}" \
    -d "${LIVE_DB_NAME}" \
    -i "${ALL_INSTALL_MODULES}" \
    -u "${ALL_UPGRADE_MODULES}" \
    --stop-after-init

echo "==> Verifying protected business-row identities after module upgrade"
capture_identity_snapshot "${IDENTITY_SNAPSHOT_AFTER}" "${PROTECTED_TABLES[@]}"
if ! diff -u "${IDENTITY_SNAPSHOT_BEFORE}" "${IDENTITY_SNAPSHOT_AFTER}"; then
  echo "ERROR: protected business-row identities changed during the module upgrade." >&2
  echo "Odoo remains stopped. Review the snapshots and encrypted backup before any recovery action." >&2
  exit 1
fi
echo "==> Protected row counts and SHA-256 identity checksums are unchanged"

echo "==> Registering verified backup marker for guarded WhatsApp maintenance"
docker compose run --rm -T --no-deps \
  -e ELSX_BACKUP_REFERENCE="${BACKUP_REFERENCE}" \
  -e ELSX_BACKUP_DATABASE="${LIVE_DB_NAME}" \
  -e ELSX_BACKUP_SHA256="${BACKUP_SHA256}" \
  -e ELSX_BACKUP_VERIFIED_AT="${BACKUP_VERIFIED_AT}" \
  odoo python3 /opt/odoo/odoo-bin shell \
    -c "${CONFIG}" -d "${LIVE_DB_NAME}" --no-http <<'PY'
import os

params = env['ir.config_parameter'].sudo()
for key, value in {
    'elsx.whatsapp.last_verified_backup.reference': os.environ['ELSX_BACKUP_REFERENCE'],
    'elsx.whatsapp.last_verified_backup.database': os.environ['ELSX_BACKUP_DATABASE'],
    'elsx.whatsapp.last_verified_backup.sha256': os.environ['ELSX_BACKUP_SHA256'],
    'elsx.whatsapp.last_verified_backup.verified_at': os.environ['ELSX_BACKUP_VERIFIED_AT'],
}.items():
    params.set_param(key, value)
env.cr.commit()
PY

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
    WHERE name IN ('elsx_client_restrictions','elsx_attendance_tracking','elsx_face_attendance','elsx_saas','elsx_ai_core','elsx_whatsapp_core','elsx_whatsapp_gateway','elsx_whatsapp_marketing','elsx_ai_marketing','elsx_ai_website_builder','elsx_tally_integration','crm','account','hr_attendance')
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
