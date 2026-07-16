#!/usr/bin/env bash
set -euo pipefail

# Safely uninstall the deactivated elsx_saas module from selected databases.
# This script does not drop databases, delete Docker volumes, delete filestore
# data, or remove custom addon source files.

DB_USER="${POSTGRES_USER:-odoo}"
CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
OUTPUT_DIR="${OUTPUT_DIR:-secure_backups}"
DB_NAME_EXCLUDES="${DB_NAME_EXCLUDES:-postgres}"
TARGET_DBS="${TARGET_DBS:-}"
CONFIRM_UNINSTALL_SAAS="${CONFIRM_UNINSTALL_SAAS:-NO}"
REPAIR_MODULES="${REPAIR_MODULES:-elsx_client_restrictions,elsx_ai_ocr}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

if [ "${CONFIRM_UNINSTALL_SAAS}" != "YES" ]; then
  echo "ERROR: set CONFIRM_UNINSTALL_SAAS=YES to uninstall elsx_saas." >&2
  echo "Example: BACKUP_PASSPHRASE=... CONFIRM_UNINSTALL_SAAS=YES TARGET_DBS=FiberaFRP_DB bash deploy/uninstall_saas_all_dbs.sh" >&2
  exit 2
fi

if [ -z "${TARGET_DBS}" ] && [ "${CONFIRM_ALL_DBS:-NO}" != "YES" ]; then
  echo "ERROR: set TARGET_DBS=db1,db2 or CONFIRM_ALL_DBS=YES." >&2
  echo "This guard prevents accidental tenant-wide module uninstalls." >&2
  exit 2
fi

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  echo "ERROR: BACKUP_PASSPHRASE is required. Refusing SaaS uninstall without encrypted backups." >&2
  exit 1
fi

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

echo "==> Ensuring PostgreSQL is running"
docker compose up -d db >/dev/null
wait_for_db

EXCLUDE_SQL="'$(echo "${DB_NAME_EXCLUDES}" | sed "s/,/','/g")'"
DB_LIST_SQL="SELECT datname
               FROM pg_database
              WHERE datistemplate = false
                AND datallowconn = true
                AND datname NOT IN (${EXCLUDE_SQL})
              ORDER BY datname;"
DB_LIST_OUTPUT="$(docker compose exec -T db psql -U "${DB_USER}" -d postgres -Atc "${DB_LIST_SQL}")"

if [ -n "${TARGET_DBS}" ]; then
  IFS=',' read -r -a REQUESTED_DATABASES <<< "${TARGET_DBS}"
  DATABASES=()
  for REQUESTED_DB in "${REQUESTED_DATABASES[@]}"; do
    REQUESTED_DB="$(echo "${REQUESTED_DB}" | xargs)"
    [ -z "${REQUESTED_DB}" ] && continue
    if ! printf '%s\n' "${DB_LIST_OUTPUT}" | grep -Fxq "${REQUESTED_DB}"; then
      echo "ERROR: requested database '${REQUESTED_DB}' was not found or is excluded." >&2
      echo "Available application databases:" >&2
      printf '%s\n' "${DB_LIST_OUTPUT}" >&2
      exit 1
    fi
    DATABASES+=("${REQUESTED_DB}")
  done
elif [ -n "${DB_LIST_OUTPUT}" ]; then
  mapfile -t DATABASES <<< "${DB_LIST_OUTPUT}"
else
  DATABASES=()
fi

if [ "${#DATABASES[@]}" -eq 0 ]; then
  echo "No application databases found. Nothing to uninstall."
  exit 0
fi

echo "==> Target databases: ${DATABASES[*]}"

for DB in "${DATABASES[@]}"; do
  echo
  echo "---- Creating encrypted backup for ${DB}"
  OUTPUT_DIR="${OUTPUT_DIR}" BACKUP_PASSPHRASE="${BACKUP_PASSPHRASE}" \
    bash deploy/export_live_encrypted_backup.sh "${DB}"
done

echo
 echo "==> Building Odoo image"
docker compose build odoo

echo "==> Stopping Odoo and optional sidecars for clean module operations"
docker compose stop sidecar >/dev/null 2>&1 || true
docker compose stop odoo >/dev/null 2>&1 || true

for DB in "${DATABASES[@]}"; do
  echo
  echo "---- Applying access/settings repair modules on ${DB}: ${REPAIR_MODULES}"
  docker compose run --rm -T --no-deps odoo \
    python3 /opt/odoo/odoo-bin \
      -c "${CONFIG}" \
      -d "${DB}" \
      -u "${REPAIR_MODULES}" \
      --stop-after-init

  echo "---- Uninstalling elsx_saas from ${DB}"
  docker compose run --rm -T --no-deps odoo \
    python3 /opt/odoo/odoo-bin shell \
      -c "${CONFIG}" \
      -d "${DB}" \
      --no-http <<'PY'
module = env['ir.module.module'].search([('name', '=', 'elsx_saas')], limit=1)
if not module:
    print('elsx_saas module record not found; nothing to uninstall.')
elif module.state == 'uninstalled':
    print('elsx_saas is already uninstalled.')
else:
    env['ir.config_parameter'].sudo().set_param('elsx_saas.enabled', '0')
    module.with_context(elsx_allow_protected_module_uninstall=True).button_immediate_uninstall()
    env.cr.commit()
    refreshed = env['ir.module.module'].search([('name', '=', 'elsx_saas')], limit=1)
    print('elsx_saas state=' + (refreshed.state or '<missing>'))
PY

  docker compose exec -T db psql -U "${DB_USER}" -d "${DB}" -c \
    "SELECT name, state, latest_version FROM ir_module_module WHERE name IN ('elsx_saas','elsx_client_restrictions','elsx_ai_ocr') ORDER BY name;" || true
done

echo
 echo "==> Starting Odoo and WhatsApp sidecar"
docker compose up -d odoo sidecar

echo "==> SaaS uninstall flow complete. Encrypted backups are in: ${OUTPUT_DIR}"
echo "Check logs with: docker logs --tail 250 odoo_app"
