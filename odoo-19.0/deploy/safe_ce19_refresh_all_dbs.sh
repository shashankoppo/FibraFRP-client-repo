#!/usr/bin/env bash
set -euo pipefail

DB_USER="${POSTGRES_USER:-odoo}"
CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
OUTPUT_DIR="${OUTPUT_DIR:-secure_backups}"
DB_NAME_EXCLUDES="${DB_NAME_EXCLUDES:-postgres}"
INSTALL_CE_PROFILE_ON_EXISTING="${INSTALL_CE_PROFILE_ON_EXISTING:-NO}"
DEFAULT_CUSTOM_MODULES="${DEFAULT_CUSTOM_MODULES:-elsx_client_restrictions,elsx_rebrand}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

if [ "${CONFIRM_ALL_DBS:-NO}" != "YES" ]; then
  echo "ERROR: set CONFIRM_ALL_DBS=YES to refresh every application database." >&2
  exit 2
fi
if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  echo "ERROR: BACKUP_PASSPHRASE is required for encrypted pre-upgrade backups." >&2
  exit 1
fi
case "${INSTALL_CE_PROFILE_ON_EXISTING}" in
  YES|NO) ;;
  *)
    echo "ERROR: INSTALL_CE_PROFILE_ON_EXISTING must be YES or NO." >&2
    exit 2
    ;;
esac

if [ "${ALLOW_DIRTY_CODE:-NO}" != "YES" ]; then
  DIRTY_STATUS="$(git status --short --untracked-files=no)"
  BLOCKING_DIRTY_STATUS="$(printf '%s\n' "${DIRTY_STATUS}" | grep -vE '^ M custom_addons/elsx_whatsapp_marketing/sidecar/package-lock\.json$' || true)"
  if [ -n "${BLOCKING_DIRTY_STATUS}" ]; then
    echo "ERROR: tracked Git files are modified. Deploy a committed revision." >&2
    printf '%s\n' "${BLOCKING_DIRTY_STATUS}" >&2
    exit 1
  fi
fi

sql_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "${value}"
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

if [[ "${OUTPUT_DIR}" != /* ]]; then
  OUTPUT_DIR="${PROJECT_DIR}/${OUTPUT_DIR}"
fi
mkdir -p "${OUTPUT_DIR}"

EXCLUDES=()
IFS=',' read -r -a RAW_EXCLUDES <<< "${DB_NAME_EXCLUDES}"
for item in "${RAW_EXCLUDES[@]}"; do
  [ -n "${item}" ] && EXCLUDES+=("$(sql_quote "${item}")")
done
EXCLUDE_SQL="$(join_csv "${EXCLUDES[@]}")"

echo "==> Latest Odoo CE refresh for all client databases"
echo "==> Existing records are preserved; every installed module is upgraded"
echo "==> Install complete CE application profile: ${INSTALL_CE_PROFILE_ON_EXISTING}"

echo "==> Ensuring PostgreSQL is running"
docker compose up -d db

mapfile -t DATABASES < <(
  docker compose exec -T db psql -X -v ON_ERROR_STOP=1     -U "${DB_USER}" -d postgres -Atc     "SELECT datname
       FROM pg_database
      WHERE datistemplate = false
        AND datallowconn = true
        AND datname NOT IN (${EXCLUDE_SQL})
      ORDER BY datname;"
)
if [ "${#DATABASES[@]}" -eq 0 ]; then
  echo "No application databases found."
  exit 0
fi
echo "==> Target databases: ${DATABASES[*]}"

echo "==> Building the latest Odoo image before backup"
docker compose build odoo

PROFILE_RUN=(
  docker compose run --rm -T --no-deps
  --entrypoint python3
  odoo /opt/odoo/deploy/ce_module_profile.py
)
CE_APPLICATION_MODULES="$("${PROFILE_RUN[@]}" --applications --format csv)"
if [ -z "${CE_APPLICATION_MODULES}" ]; then
  echo "ERROR: official CE application profile is empty." >&2
  exit 1
fi

for DB in "${DATABASES[@]}"; do
  echo
  echo "---- Creating encrypted database and filestore backup for ${DB}"
  OUTPUT_DIR="${OUTPUT_DIR}" BACKUP_PASSPHRASE="${BACKUP_PASSPHRASE}"     bash deploy/export_live_encrypted_backup.sh "${DB}"
done

SERVICES_STOPPED=NO
restart_services_on_exit() {
  local status=$?
  trap - EXIT
  if [ "${SERVICES_STOPPED}" = "YES" ]; then
    echo "==> Restarting Odoo services"
    if ! docker compose up -d odoo sidecar; then
      echo "ERROR: failed to restart Odoo services." >&2
      status=1
    fi
  fi
  exit "${status}"
}
trap restart_services_on_exit EXIT

echo
echo "==> Stopping Odoo and sidecar for consistent registry upgrades"
docker compose stop sidecar >/dev/null 2>&1 || true
docker compose stop odoo >/dev/null 2>&1 || true
SERVICES_STOPPED=YES

for DB in "${DATABASES[@]}"; do
  echo
  echo "---- Preparing module refresh for ${DB}"
  MODULE_ARGS=(-u all)

  if [ "${INSTALL_CE_PROFILE_ON_EXISTING}" = "YES" ]; then
    COUNTRY_CSV="$(
      docker compose exec -T db psql -X -v ON_ERROR_STOP=1         -U "${DB_USER}" -d "${DB}" -Atc         "SELECT COALESCE(string_agg(DISTINCT upper(country.code), ','), '')
           FROM res_company company
           JOIN res_partner partner ON partner.id = company.partner_id
           JOIN res_country country ON country.id = partner.country_id;"
    )"
    PROFILE_ARGS=(--applications --format csv)
    IFS=',' read -r -a COUNTRIES <<< "${COUNTRY_CSV}"
    for COUNTRY in "${COUNTRIES[@]}"; do
      [ -n "${COUNTRY}" ] && PROFILE_ARGS+=(--country "${COUNTRY}")
    done
    CE_PROFILE_MODULES="$("${PROFILE_RUN[@]}" "${PROFILE_ARGS[@]}")"
    INSTALL_MODULES="$(join_csv "${CE_PROFILE_MODULES}" "${DEFAULT_CUSTOM_MODULES}")"
    MODULE_ARGS=(-i "${INSTALL_MODULES}" -u all)
    echo "---- Countries: ${COUNTRY_CSV:-not configured}"
    echo "---- Installing official CE application/localization profile"
  fi

  echo "---- Upgrading every installed module on ${DB}"
  docker compose run --rm -T --no-deps     -e ELSX_NATIVE_ADMIN_CLEANUP=NO     odoo     python3 /opt/odoo/odoo-bin       -c "${CONFIG}"       -d "${DB}"       "${MODULE_ARGS[@]}"       --without-demo=True       --stop-after-init       --no-http

  PENDING="$(
    docker compose exec -T db psql -X -v ON_ERROR_STOP=1       -U "${DB_USER}" -d "${DB}" -Atc       "SELECT COALESCE(string_agg(name || ':' || state, ',' ORDER BY name), '')
         FROM ir_module_module
        WHERE state IN ('to install', 'to upgrade', 'to remove');"
  )"
  if [ -n "${PENDING}" ]; then
    echo "ERROR: pending module states remain on ${DB}: ${PENDING}" >&2
    exit 1
  fi
  echo "---- ${DB} module registry is clean"
done

echo
echo "==> Starting Odoo and sidecar"
docker compose up -d odoo sidecar
SERVICES_STOPPED=NO

echo "==> Verifying container health"
docker compose ps
docker compose exec -T odoo curl -fsS http://127.0.0.1:8069/web/health >/dev/null

echo
echo "==> Odoo CE refresh complete for all client databases"
echo "Encrypted backups: ${OUTPUT_DIR}"
echo "Profile installation on existing DBs: ${INSTALL_CE_PROFILE_ON_EXISTING}"
