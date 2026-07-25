#!/usr/bin/env bash
set -euo pipefail

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-odoo}"
DB_PASSWORD="${DB_PASSWORD:-}"
ODOO_CONFIG="${ODOO_RC:-/etc/odoo/odoo.conf}"
ODOO_BIN="${ODOO_BIN:-/opt/odoo/odoo-bin}"
BACKUP_DIR="${ELSX_AUTO_UPGRADE_BACKUP_DIR:-/backups/auto-upgrade}"
INSTALL_MODULES="${ELSX_AUTO_INSTALL_MODULES:-elsx_client_restrictions,elsx_ai_core,elsx_whatsapp_core,elsx_whatsapp_gateway}"
UPGRADE_MODULES="${ELSX_AUTO_UPGRADE_MODULES:-elsx_client_restrictions,elsx_ai_core,elsx_whatsapp_core,elsx_whatsapp_gateway,elsx_whatsapp_marketing,elsx_ai_marketing,elsx_ai_website_builder}"
MARKER_KEY="elsx.auto_upgrade.release"

log() {
  printf '[auto-upgrade] %s\n' "$*" >&2
}

is_enabled() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

psql_db() {
  local database="$1"
  shift
  PGPASSWORD="${DB_PASSWORD}" psql \
    -X -v ON_ERROR_STOP=1 \
    -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${database}" \
    "$@"
}

compute_release() {
  python3 - <<'PY'
import hashlib
from pathlib import Path

base = Path('/opt/odoo')
roots = [
    base / 'custom_addons' / 'elsx_ai_core',
    base / 'custom_addons' / 'elsx_ai_marketing',
    base / 'custom_addons' / 'elsx_ai_website_builder',
    base / 'custom_addons' / 'elsx_client_restrictions',
    base / 'custom_addons' / 'elsx_whatsapp_core',
    base / 'custom_addons' / 'elsx_whatsapp_gateway',
    base / 'custom_addons' / 'elsx_whatsapp_marketing',
    base / 'deploy' / 'removal_capsules' / 'elsx_saas',
]
files = [
    base / 'deploy' / 'auto_upgrade_on_start.sh',
    base / 'deploy' / 'remove_retired_saas_db.sh',
]
extensions = {'.py', '.xml', '.csv', '.js', '.css', '.sh'}
digest = hashlib.sha256()
paths = {
    file
    for root in roots
    if root.exists()
    for file in root.rglob('*')
    if file.is_file()
    and file.suffix in extensions
    and '__pycache__' not in file.parts
}
paths.update(file for file in files if file.exists())
for path in sorted(paths):
    digest.update(path.relative_to(base).as_posix().encode())
    digest.update(b'\0')
    digest.update(path.read_bytes())
    digest.update(b'\0')
print(digest.hexdigest()[:24])
PY
}

capture_identity_snapshot() {
  local database="$1"
  local output_file="$2"
  shift 2
  local table count checksum

  : > "${output_file}"
  for table in "$@"; do
    if [[ ! "${table}" =~ ^[a-z0-9_]+$ ]]; then
      log "Refusing unexpected table name ${table}."
      return 1
    fi
    count="$(psql_db "${database}" -Atc "SELECT count(*) FROM ${table};")"
    checksum="$(
      psql_db "${database}" -Atc "COPY (SELECT id FROM ${table} ORDER BY id) TO STDOUT" \
        | sha256sum | awk '{print $1}'
    )"
    printf '%s|%s|%s\n' "${table}" "${count}" "${checksum}" >> "${output_file}"
  done

  count="$(
    psql_db "${database}" -Atc \
      "SELECT count(*) FROM ir_attachment WHERE res_model LIKE 'whatsapp.%' OR res_model LIKE 'elsx.ai.%';"
  )"
  checksum="$(
    psql_db "${database}" -Atc \
      "COPY (SELECT id FROM ir_attachment WHERE res_model LIKE 'whatsapp.%' OR res_model LIKE 'elsx.ai.%' ORDER BY id) TO STDOUT" \
      | sha256sum | awk '{print $1}'
  )"
  printf '%s|%s|%s\n' 'ir_attachment_whatsapp_ai' "${count}" "${checksum}" >> "${output_file}"

  count="$(
    psql_db "${database}" -Atc \
      "SELECT count(*) FROM ir_attachment
        WHERE COALESCE(res_model, '') NOT LIKE 'elsx.saas.%'
          AND COALESCE(url, '') NOT LIKE '/web/assets/%';"
  )"
  checksum="$(
    psql_db "${database}" -Atc \
      "COPY (
         SELECT id, COALESCE(store_fname, ''), COALESCE(checksum, '')
           FROM ir_attachment
          WHERE COALESCE(res_model, '') NOT LIKE 'elsx.saas.%'
            AND COALESCE(url, '') NOT LIKE '/web/assets/%'
          ORDER BY id
       ) TO STDOUT" \
      | sha256sum | awk '{print $1}'
  )"
  printf '%s|%s|%s\n' 'ir_attachment_non_saas' "${count}" "${checksum}" >> "${output_file}"
}

verify_encrypted_backup() {
  local backup_file="$1"
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -pass env:ELSX_AUTO_BACKUP_SECRET -in "${backup_file}" 2>/dev/null \
    | pg_restore --list >/dev/null
}

create_or_verify_backup() {
  local database="$1"
  local safe_database="$2"
  local safe_release="$3"
  local backup_file="${BACKUP_DIR}/${safe_database}_pre_${safe_release}.pg_dump.enc"
  local temp_file="${backup_file}.tmp.$$"
  local checksum checksum_file

  if [ -s "${backup_file}" ]; then
    log "Reusing verified pre-upgrade backup for ${database}: ${backup_file}"
    verify_encrypted_backup "${backup_file}"
  else
    log "Creating encrypted pre-upgrade backup for ${database}."
    PGPASSWORD="${DB_PASSWORD}" pg_dump \
      -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${database}" \
      --format=custom --no-owner \
      | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
          -pass env:ELSX_AUTO_BACKUP_SECRET -out "${temp_file}"
    verify_encrypted_backup "${temp_file}"
    chmod 600 "${temp_file}"
    mv "${temp_file}" "${backup_file}"
  fi

  checksum="$(sha256sum "${backup_file}" | awk '{print $1}')"
  checksum_file="${backup_file}.sha256"
  printf '%s  %s\n' "${checksum}" "$(basename "${backup_file}")" > "${checksum_file}"
  chmod 600 "${checksum_file}"
  printf '%s|%s\n' "${backup_file}" "${checksum}"
}

upgrade_database() {
  local database="$1"
  local release="$2"
  local safe_release="$3"
  local safe_database backup_result backup_file backup_sha verified_at
  local before_snapshot after_snapshot installed_count protected_table_list
  local bridge_was_present shell_was_installed shell_is_installed
  local saas_was_installed
  local expected_backup_file snapshot_temp
  local -a protected_tables

  safe_database="$(printf '%s' "${database}" | tr -c 'A-Za-z0-9_.-' '_')"
  bridge_was_present="$(
    psql_db "${database}" -Atc "SELECT count(*) FROM ir_module_module
      WHERE name IN (
        'elsx_whatsapp_core', 'elsx_whatsapp_gateway', 'elsx_whatsapp_marketing'
      ) AND state IN ('installed', 'to upgrade', 'to install');"
  )"
  shell_was_installed="$(
    psql_db "${database}" -Atc "SELECT count(*) FROM ir_module_module
      WHERE name = 'elsx_whatsapp_marketing'
        AND state IN ('installed', 'to upgrade', 'to install');"
  )"
  saas_was_installed="$(
    psql_db "${database}" -Atc "SELECT count(*) FROM ir_module_module
      WHERE name = 'elsx_saas'
        AND state != 'uninstalled';"
  )"
  protected_table_list="$(
    psql_db "${database}" -Atc \
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
  )"
  mapfile -t protected_tables <<< "${protected_table_list}"

  expected_backup_file="${BACKUP_DIR}/${safe_database}_pre_${safe_release}.pg_dump.enc"
  before_snapshot="${expected_backup_file}.identity"
  if [ -s "${before_snapshot}" ]; then
    log "Reusing original protected-row identities for ${database}."
  else
    snapshot_temp="${before_snapshot}.tmp.$$"
    capture_identity_snapshot "${database}" "${snapshot_temp}" "${protected_tables[@]}"
    chmod 600 "${snapshot_temp}"
    mv "${snapshot_temp}" "${before_snapshot}"
  fi

  backup_result="$(create_or_verify_backup "${database}" "${safe_database}" "${safe_release}")"
  backup_file="${backup_result%|*}"
  backup_sha="${backup_result##*|}"
  after_snapshot="$(mktemp)"

  if [ "${saas_was_installed}" != '0' ]; then
    log "Uninstalling the retired SaaS module from ${database}."
    if ! bash /opt/odoo/deploy/remove_retired_saas_db.sh "${database}"; then
      log "SaaS did not uninstall cleanly in ${database}; Odoo will not start."
      log "Verified recovery backup: ${backup_file}"
      return 1
    fi
  fi

  if [ "${bridge_was_present}" != '0' ]; then
    log "Installing/upgrading native administration cleanup, AI, and WhatsApp modules in ${database}."
    python3 "${ODOO_BIN}" \
      -c "${ODOO_CONFIG}" \
      --db_host="${DB_HOST}" \
      --db_port="${DB_PORT}" \
      --db_user="${DB_USER}" \
      --db_password="${DB_PASSWORD}" \
      -d "${database}" \
      -i "${INSTALL_MODULES}" \
      -u "${UPGRADE_MODULES}" \
      --without-demo=True \
      --stop-after-init \
      --no-http \
      --log-level=error
  else
    log "Installing/upgrading native administration cleanup in ${database}."
    python3 "${ODOO_BIN}" \
      -c "${ODOO_CONFIG}" \
      --db_host="${DB_HOST}" \
      --db_port="${DB_PORT}" \
      --db_user="${DB_USER}" \
      --db_password="${DB_PASSWORD}" \
      -d "${database}" \
      -i elsx_client_restrictions \
      -u elsx_client_restrictions \
      --without-demo=True \
      --stop-after-init \
      --no-http \
      --log-level=error
  fi

  capture_identity_snapshot "${database}" "${after_snapshot}" "${protected_tables[@]}"
  if ! diff -u "${before_snapshot}" "${after_snapshot}"; then
    rm -f "${after_snapshot}"
    log "Protected client-row identities changed in ${database}; Odoo will not start."
    log "Verified recovery backup: ${backup_file}"
    return 1
  fi
  rm -f "${after_snapshot}"

  if [ "${bridge_was_present}" != '0' ]; then
    installed_count="$(
      psql_db "${database}" -Atc \
        "SELECT count(*) FROM ir_module_module
          WHERE name IN (
            'elsx_client_restrictions', 'elsx_ai_core', 'elsx_whatsapp_core',
            'elsx_whatsapp_gateway'
          ) AND state = 'installed';"
    )"
    if [ "${installed_count}" != '4' ]; then
      log "Required persistent WhatsApp bridge modules are not all installed in ${database}; Odoo will not start."
      return 1
    fi
  fi

  shell_is_installed="$(
    psql_db "${database}" -Atc "SELECT count(*) FROM ir_module_module
      WHERE name = 'elsx_whatsapp_marketing'
        AND state = 'installed';"
  )"
  if [ "${shell_is_installed}" != "${shell_was_installed}" ]; then
    log "WhatsApp application lifecycle changed unexpectedly in ${database}; Odoo will not start."
    return 1
  fi

  verified_at="$(date -u '+%Y-%m-%d %H:%M:%S')"
  ELSX_AUTO_RELEASE="${release}" \
  ELSX_BACKUP_REFERENCE="$(basename "${backup_file}")" \
  ELSX_BACKUP_DATABASE="${database}" \
  ELSX_BACKUP_SHA256="${backup_sha}" \
  ELSX_BACKUP_VERIFIED_AT="${verified_at}" \
  python3 "${ODOO_BIN}" shell \
    -c "${ODOO_CONFIG}" \
    --db_host="${DB_HOST}" \
    --db_port="${DB_PORT}" \
    --db_user="${DB_USER}" \
    --db_password="${DB_PASSWORD}" \
    -d "${database}" --no-http --log-level=error <<'PY'
import os

params = env['ir.config_parameter'].sudo()
for key, value in {
    'elsx.auto_upgrade.release': os.environ['ELSX_AUTO_RELEASE'],
    'elsx.whatsapp.last_verified_backup.reference': os.environ['ELSX_BACKUP_REFERENCE'],
    'elsx.whatsapp.last_verified_backup.database': os.environ['ELSX_BACKUP_DATABASE'],
    'elsx.whatsapp.last_verified_backup.sha256': os.environ['ELSX_BACKUP_SHA256'],
    'elsx.whatsapp.last_verified_backup.verified_at': os.environ['ELSX_BACKUP_VERIFIED_AT'],
}.items():
    params.set_param(key, value)
env.cr.commit()
PY

  log "Database ${database} is ready for release ${release}."
}

if ! is_enabled "${ELSX_AUTO_UPGRADE:-YES}"; then
  log 'Automatic database upgrades are disabled by ELSX_AUTO_UPGRADE.'
  exit 0
fi

if [ -z "${DB_PASSWORD}" ]; then
  log 'DB_PASSWORD is required for backup and migration safety.'
  exit 1
fi

release="${ELSX_AUTO_UPGRADE_RELEASE:-$(compute_release)}"
safe_release="$(printf '%s' "${release}" | tr -c 'A-Za-z0-9_.-' '_')"
backup_secret="${BACKUP_PASSPHRASE:-${ELSX_AUTO_UPGRADE_BACKUP_PASSPHRASE:-${DB_PASSWORD}}}"
if [ -z "${backup_secret}" ]; then
  log 'A backup passphrase or database password is required; refusing to migrate.'
  exit 1
fi
if [ -z "${BACKUP_PASSPHRASE:-${ELSX_AUTO_UPGRADE_BACKUP_PASSPHRASE:-}}" ]; then
  log 'BACKUP_PASSPHRASE is unset; using DB_PASSWORD for encrypted pre-upgrade backups.'
fi
export ELSX_AUTO_BACKUP_SECRET="${backup_secret}"
unset backup_secret

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"
umask 077

database_list="$(
  psql_db postgres -Atc \
    "SELECT datname FROM pg_database
      WHERE datistemplate = false
        AND datallowconn = true
        AND datname <> 'postgres'
      ORDER BY datname;"
)"
databases=()
while IFS= read -r database; do
  if [ -n "${database}" ]; then
    databases+=("${database}")
  fi
done <<< "${database_list}"

pending=0
for database in "${databases[@]}"; do
  has_modules="$(
    psql_db "${database}" -Atc "SELECT to_regclass('public.ir_module_module') IS NOT NULL;"
  )"
  if [ "${has_modules}" != 't' ]; then
    log "Skipping non-Odoo database ${database}."
    continue
  fi

  current_release="$(
    psql_db "${database}" -Atc \
      "SELECT value FROM ir_config_parameter WHERE key = '${MARKER_KEY}' LIMIT 1;"
  )"
  if [ "${current_release}" = "${release}" ]; then
    log "Database ${database} is already current (${release})."
    continue
  fi

  pending=1
  upgrade_database "${database}" "${release}" "${safe_release}"
done

if [ "${pending}" = '0' ]; then
  log "No database migration is required for release ${release}."
else
  log "All eligible databases passed backup, migration, and identity verification for ${release}."
fi
