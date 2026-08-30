#!/usr/bin/env bash
set -euo pipefail

if [ "${ODOO_AUTO_UPDATE_ON_START:-YES}" != "YES" ]; then
  echo "[auto-update] Disabled by ODOO_AUTO_UPDATE_ON_START."
  exit 0
fi

CONFIG="${ODOO_RC:-/etc/odoo/odoo.conf}"
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-odoo}"
DB_PASSWORD="${DB_PASSWORD:-odoo}"
ADDONS_PATH="${ODOO_EFFECTIVE_ADDONS_PATH:-/opt/odoo/addons,/opt/odoo/odoo/addons,/opt/odoo/custom_addons,/opt/odoo/custom_addons/elsx_stubs,/opt/odoo/third_party_addons}"
INSTALL_MODULES="${ODOO_AUTO_INSTALL_MODULES:-}"
ALLOW_INSTALL="${ODOO_AUTO_ALLOW_INSTALL:-NO}"
UPGRADE_MODULES="${ODOO_AUTO_UPDATE_MODULES:-all}"
DB_EXCLUDES="${ODOO_AUTO_UPDATE_DB_EXCLUDES:-postgres}"
TARGET_DB="${ODOO_AUTO_UPDATE_DB_NAME:-}"
BACKUP_ON_UPDATE="${ODOO_AUTO_BACKUP_ON_UPDATE:-YES}"
BACKUP_DIR="${ODOO_AUTO_BACKUP_DIR:-/opt/odoo/secure_backups/auto}"
MARKER_KEY="${ODOO_AUTO_UPDATE_MARKER_KEY:-fibrafrp.auto_update_fingerprint}"

export PGPASSWORD="${DB_PASSWORD}"

log() {
  printf '[auto-update] %s\n' "$*"
}

if [ -n "${INSTALL_MODULES}" ] && [ "${ALLOW_INSTALL}" != "YES" ]; then
  echo "ERROR: ODOO_AUTO_INSTALL_MODULES is set, but ODOO_AUTO_ALLOW_INSTALL is not YES." >&2
  echo "This production startup path is locked to updates only by default." >&2
  exit 1
fi

sql_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "${value}"
}

quote_csv_for_sql() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/''/g; s/,/','/g")"
}

join_csv() {
  local result=""
  local item
  for item in "$@"; do
    [ -n "${item}" ] || continue
    if [ -z "${result}" ]; then
      result="${item}"
    else
      result="${result},${item}"
    fi
  done
  printf '%s' "${result}"
}

csv_contains_all() {
  local csv="$1"
  local item
  IFS=',' read -r -a ITEMS <<< "${csv}"
  for item in "${ITEMS[@]}"; do
    item="${item//[[:space:]]/}"
    if [ "${item}" = "all" ]; then
      return 0
    fi
  done
  return 1
}

csv_without_all() {
  local csv="$1"
  local result=""
  local item
  IFS=',' read -r -a ITEMS <<< "${csv}"
  for item in "${ITEMS[@]}"; do
    item="${item//[[:space:]]/}"
    [ -n "${item}" ] || continue
    [ "${item}" = "all" ] && continue
    result="$(join_csv "${result}" "${item}")"
  done
  printf '%s' "${result}"
}

fingerprint_source() {
  (
    cd /opt/odoo
    {
      printf 'addons_path=%s\n' "${ADDONS_PATH}"
      printf 'install_modules=%s\n' "${INSTALL_MODULES}"
      printf 'upgrade_modules=%s\n' "${UPGRADE_MODULES}"
      [ -f requirements.txt ] && sha256sum requirements.txt
      find addons odoo/addons custom_addons third_party_addons \
        -type f \( \
          -name "__manifest__.py" \
          -o -name "*.xml" \
          -o -name "*.csv" \
          -o -name "*.py" \
          -o -name "requirements.txt" \
        \) -print0 2>/dev/null \
        | sort -z \
        | xargs -0 -r sha256sum
    } | sha256sum | awk '{print $1}'
  )
}

table_exists() {
  local database="$1"
  local table="$2"
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${database}" -Atc \
    "SELECT to_regclass($(sql_quote "public.${table}")) IS NOT NULL;" | tr -d '\r'
}

installed_modules_for_db() {
  local database="$1"
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${database}" -Atc \
    "SELECT COALESCE(string_agg(name, ',' ORDER BY name), '')
       FROM ir_module_module
      WHERE state IN ('installed', 'to upgrade');" | tr -d '\r'
}

blocked_pending_states_for_db() {
  local database="$1"
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${database}" -Atc \
    "SELECT COALESCE(string_agg(name || ':' || state, ',' ORDER BY name), '')
       FROM ir_module_module
      WHERE state IN ('to install', 'to remove');" | tr -d '\r'
}

new_installed_modules_for_db() {
  local database="$1"
  local before_csv="$2"
  local before_sql
  before_sql="$(quote_csv_for_sql "${before_csv}")"
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${database}" -Atc \
    "SELECT COALESCE(string_agg(name, ',' ORDER BY name), '')
       FROM ir_module_module
      WHERE state = 'installed'
        AND name NOT IN (${before_sql});" | tr -d '\r'
}

stored_fingerprint_for_db() {
  local database="$1"
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${database}" -Atc \
    "SELECT COALESCE((SELECT value FROM ir_config_parameter WHERE key = $(sql_quote "${MARKER_KEY}") LIMIT 1), '');" | tr -d '\r'
}

store_fingerprint_for_db() {
  local database="$1"
  local fingerprint="$2"
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${database}" -v ON_ERROR_STOP=1 -c \
    "INSERT INTO ir_config_parameter(key, value)
     VALUES ($(sql_quote "${MARKER_KEY}"), $(sql_quote "${fingerprint}"))
     ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;" >/dev/null
}

backup_db() {
  local database="$1"
  mkdir -p "${BACKUP_DIR}"
  local stamp
  stamp="$(date -u +%Y%m%d_%H%M%S)"
  local file="${BACKUP_DIR}/${database}_${stamp}.pg_dump"
  log "Backing up ${database} to ${file}"
  pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${database}" --format=custom -f "${file}"
  if [ ! -s "${file}" ]; then
    echo "ERROR: backup file was not created: ${file}" >&2
    exit 1
  fi
}

SOURCE_FINGERPRINT="$(fingerprint_source)"
log "Source fingerprint: ${SOURCE_FINGERPRINT}"

if [ -f /opt/odoo/deploy/audit_addons_ready.py ]; then
  log "Auditing addon paths"
  python3 /opt/odoo/deploy/audit_addons_ready.py
fi

if [ -n "${TARGET_DB}" ]; then
  mapfile -t DATABASES < <(
    psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres -Atc \
      "SELECT datname
         FROM pg_database
        WHERE datistemplate = false
          AND datallowconn = true
          AND datname = $(sql_quote "${TARGET_DB}")
        ORDER BY datname;" | tr -d '\r'
  )
else
  EXCLUDE_SQL="$(quote_csv_for_sql "${DB_EXCLUDES}")"
  mapfile -t DATABASES < <(
    psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d postgres -Atc \
      "SELECT datname
         FROM pg_database
        WHERE datistemplate = false
          AND datallowconn = true
          AND datname NOT IN (${EXCLUDE_SQL})
        ORDER BY datname;" | tr -d '\r'
  )
fi

if [ "${#DATABASES[@]}" -eq 0 ]; then
  log "No application databases found. Starting Odoo normally."
  exit 0
fi

for DB in "${DATABASES[@]}"; do
  if [ "$(table_exists "${DB}" ir_module_module)" != "t" ] || [ "$(table_exists "${DB}" ir_config_parameter)" != "t" ]; then
    log "${DB}: not initialized yet; skipping module auto-update."
    continue
  fi

  CURRENT_FINGERPRINT="$(stored_fingerprint_for_db "${DB}")"
  if [ "${CURRENT_FINGERPRINT}" = "${SOURCE_FINGERPRINT}" ]; then
    log "${DB}: already updated for this source."
    continue
  fi

  DB_UPGRADE_MODULES="${UPGRADE_MODULES}"
  INSTALLED_MODULES="$(installed_modules_for_db "${DB}")"
  if [ -z "${INSTALLED_MODULES}" ]; then
    log "${DB}: no installed modules found; skipping."
    continue
  fi

  BLOCKED_PENDING="$(blocked_pending_states_for_db "${DB}")"
  if [ -n "${BLOCKED_PENDING}" ]; then
    echo "ERROR: ${DB} already has pending install/remove states: ${BLOCKED_PENDING}" >&2
    echo "Refusing automatic startup update until these states are handled manually." >&2
    exit 1
  fi

  if csv_contains_all "${DB_UPGRADE_MODULES}"; then
    DB_UPGRADE_MODULES="$(join_csv "${INSTALLED_MODULES}" "$(csv_without_all "${DB_UPGRADE_MODULES}")")"
  fi

  if [ "${ALLOW_INSTALL}" != "YES" ] && [ -f /opt/odoo/deploy/audit_addons_ready.py ]; then
    log "${DB}: checking that upgrade will not require new module installs"
    python3 /opt/odoo/deploy/audit_addons_ready.py \
      --addons-path "${ADDONS_PATH}" \
      --installed-modules "${INSTALLED_MODULES}" \
      --target-modules "${DB_UPGRADE_MODULES}" \
      --require-installed-dependencies
  fi

  if [ "${BACKUP_ON_UPDATE}" = "YES" ]; then
    backup_db "${DB}"
  fi

  log "${DB}: updating Apps list and upgrading installed modules"
  ODOO_MODULE_ARGS=()
  if [ -n "${INSTALL_MODULES}" ]; then
    ODOO_MODULE_ARGS+=("-i" "${INSTALL_MODULES}")
  fi
  if [ -n "${DB_UPGRADE_MODULES}" ]; then
    ODOO_MODULE_ARGS+=("-u" "${DB_UPGRADE_MODULES}")
  fi

  python3 /opt/odoo/odoo-bin \
    -c "${CONFIG}" \
    --addons-path="${ADDONS_PATH}" \
    --db_host="${DB_HOST}" \
    --db_port="${DB_PORT}" \
    --db_user="${DB_USER}" \
    --db_password="${DB_PASSWORD}" \
    -d "${DB}" \
    "${ODOO_MODULE_ARGS[@]}" \
    --without-demo=True \
    --stop-after-init \
    --no-http

  PENDING="$(
    psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB}" -Atc \
      "SELECT COALESCE(string_agg(name || ':' || state, ',' ORDER BY name), '')
         FROM ir_module_module
        WHERE state IN ('to install', 'to upgrade', 'to remove');" | tr -d '\r'
  )"
  if [ -n "${PENDING}" ]; then
    echo "ERROR: pending module states remain on ${DB}: ${PENDING}" >&2
    exit 1
  fi

  if [ "${ALLOW_INSTALL}" != "YES" ]; then
    NEWLY_INSTALLED="$(new_installed_modules_for_db "${DB}" "${INSTALLED_MODULES}")"
    if [ -n "${NEWLY_INSTALLED}" ]; then
      echo "ERROR: ${DB} installed new modules during locked update: ${NEWLY_INSTALLED}" >&2
      echo "Refusing to mark this source as applied. Review the database before restarting." >&2
      exit 1
    fi
  fi

  store_fingerprint_for_db "${DB}" "${SOURCE_FINGERPRINT}"
  log "${DB}: done."
done
