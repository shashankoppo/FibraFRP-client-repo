#!/usr/bin/env bash
set -euo pipefail

case "${ELSX_NATIVE_ADMIN_CLEANUP:-YES}" in
  1|true|TRUE|yes|YES|on|ON) ;;
  *)
    echo "[native-admin-cleanup] Disabled by ELSX_NATIVE_ADMIN_CLEANUP."
    exit 0
    ;;
esac

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-odoo}"
DB_PASSWORD="${DB_PASSWORD:-}"
ODOO_CONFIG="${ODOO_RC:-/etc/odoo/odoo.conf}"
ODOO_BIN="${ODOO_BIN:-/opt/odoo/odoo-bin}"
TARGET_DBS="${ELSX_NATIVE_ADMIN_CLEANUP_DBS:-}"
EXPECTED_MODULE_VERSIONS="'2.8.0','19.0.2.8.0'"
EXPECTED_REBRAND_VERSIONS="'1.1.1','19.0.1.1.1'"

log() {
  printf '[native-admin-cleanup] %s\n' "$*" >&2
}

if [ -z "${DB_PASSWORD}" ]; then
  log 'DB_PASSWORD is empty; skipping cleanup.'
  exit 0
fi

psql_db() {
  local database="$1"
  shift
  PGPASSWORD="${DB_PASSWORD}" psql \
    -X -v ON_ERROR_STOP=1 \
    -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${database}" \
    "$@"
}

if [ -n "${TARGET_DBS}" ]; then
  database_list="$(printf '%s' "${TARGET_DBS}" | tr ',' '\n')"
else
  if ! database_list="$(
    psql_db postgres -Atc \
      "SELECT datname FROM pg_database
        WHERE datistemplate = false
          AND datallowconn = true
          AND datname <> 'postgres'
        ORDER BY datname;"
  )"; then
    log 'Could not connect to PostgreSQL for startup cleanup; Odoo will start without applying cleanup/rebrand.'
    exit 0
  fi
fi

while IFS= read -r database; do
  [ -n "${database}" ] || continue

  if ! has_modules="$(
    psql_db "${database}" -Atc "SELECT to_regclass('public.ir_module_module') IS NOT NULL;"
  )"; then
    log "Skipping ${database}; could not inspect module table."
    continue
  fi
  if [ "${has_modules}" != 't' ]; then
    log "Skipping non-Odoo database ${database}."
    continue
  fi

  if ! needs_cleanup="$(
    psql_db "${database}" -Atc "
      SELECT CASE WHEN
        NOT EXISTS (
          SELECT 1
            FROM ir_module_module
           WHERE name = 'elsx_client_restrictions'
             AND state = 'installed'
        )
        OR EXISTS (
          SELECT 1
            FROM ir_module_module
           WHERE name = 'elsx_client_restrictions'
             AND state = 'installed'
             AND COALESCE(latest_version, '') NOT IN (${EXPECTED_MODULE_VERSIONS})
        )
        OR EXISTS (
          SELECT 1
            FROM ir_model_data
           WHERE module = 'elsx_client_restrictions'
             AND name IN (
               'menu_elsx_module_safety',
               'action_elsx_module_safety_wizard',
               'view_elsx_module_safety_wizard_form',
               'group_secret_apps_access',
               'action_apps_password_gate',
               'view_apps_password_unlock_form'
             )
        )
        OR EXISTS (
          SELECT 1
            FROM ir_ui_menu
           WHERE COALESCE(name::text, '') ILIKE '%Safe Module Change%'
        )
        OR EXISTS (
          SELECT 1
            FROM ir_config_parameter
           WHERE key = 'elsx_client_restrictions.apps_secret_token'
        )
        OR NOT EXISTS (
          SELECT 1
            FROM ir_config_parameter
           WHERE key = 'elsx_client_restrictions.apps_password_hash'
        )
        OR NOT EXISTS (
          SELECT 1
            FROM ir_module_module
           WHERE name = 'elsx_rebrand'
             AND state = 'installed'
        )
        OR EXISTS (
          SELECT 1
            FROM ir_module_module
           WHERE name = 'elsx_rebrand'
             AND state = 'installed'
             AND COALESCE(latest_version, '') NOT IN (${EXPECTED_REBRAND_VERSIONS})
        )
      THEN 't' ELSE 'f' END;"
  )"; then
    log "Skipping ${database}; could not inspect cleanup/rebrand state."
    continue
  fi

  if [ "${needs_cleanup}" != 't' ]; then
    log "${database} already has native administration metadata, Apps lock, and ELSxGlobal rebrand."
    continue
  fi

  log "Applying native administration cleanup, Apps lock, and ELSxGlobal rebrand in ${database}."
  if ! python3 "${ODOO_BIN}" \
    -c "${ODOO_CONFIG}" \
    --db_host="${DB_HOST}" \
    --db_port="${DB_PORT}" \
    --db_user="${DB_USER}" \
    --db_password="${DB_PASSWORD}" \
    -d "${database}" \
    -i elsx_client_restrictions,elsx_rebrand \
    -u elsx_client_restrictions,elsx_rebrand \
    --without-demo=True \
    --stop-after-init \
    --no-http \
    --log-level=error; then
    log "Cleanup/rebrand failed in ${database}; Odoo will continue startup so the database can be inspected."
  fi

done <<< "${database_list}"