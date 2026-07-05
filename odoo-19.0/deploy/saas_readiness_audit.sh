#!/usr/bin/env bash
set -euo pipefail

# Read-only SaaS readiness audit.
# This script does not create, update, delete, install, upgrade, or restart anything.

DB_USER="${POSTGRES_USER:-odoo}"
DB_NAME_EXCLUDES="${DB_NAME_EXCLUDES:-postgres}"
MASTER_DB="${MASTER_DB:-}"
PRIMARY_CLIENT_DB="${PRIMARY_CLIENT_DB:-FiberaFRP_DB}"
REPORT_DIR="${REPORT_DIR:-reports}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

mkdir -p "${REPORT_DIR}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
REPORT_FILE="${REPORT_DIR}/saas_readiness_${STAMP}.txt"

section() {
  echo
  echo "==== $* ===="
}

run() {
  echo "+ $*"
  "$@" || true
}

psql_db() {
  local db="$1"
  local sql="$2"
  docker compose exec -T db psql -U "${DB_USER}" -d "${db}" -Atc "${sql}" 2>/dev/null || true
}

table_exists() {
  local db="$1"
  local table="$2"
  [ "$(psql_db "${db}" "SELECT to_regclass('${table}') IS NOT NULL;")" = "t" ]
}

database_exists() {
  local db="$1"
  local escaped
  escaped="$(printf "%s" "${db}" | sed "s/'/''/g")"
  [ "$(psql_db postgres "SELECT 1 FROM pg_database WHERE datname = '${escaped}';")" = "1" ]
}

{
  echo "ELSxGlobal SaaS Readiness Audit"
  echo "Generated UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Project: ${PROJECT_DIR}"
  echo "Primary client DB: ${PRIMARY_CLIENT_DB}"
  [ -n "${MASTER_DB}" ] && echo "Master admin DB: ${MASTER_DB}"

  section "Repository State"
  run git rev-parse --show-toplevel
  run git rev-parse --short HEAD
  run git status --short --untracked-files=no

  section "Docker Compose"
  run docker compose config --quiet
  run docker compose ps

  section "Configured Runtime Limits"
  if [ -f docker-compose.yml ]; then
    grep -nE "memory:|cpus:|container_name:|profiles:" docker-compose.yml || true
  fi

  section "Odoo Config SaaS-Relevant Lines"
  if [ -f odoo.docker.conf ]; then
    grep -nE "^(list_db|dbfilter|db_name|server_wide_modules|proxy_mode|max_cron_threads|limit_memory|db_maxconn)" odoo.docker.conf || true
    grep -nE "^[;#] ?(dbfilter|db_name)" odoo.docker.conf || true
  else
    echo "odoo.docker.conf not found"
  fi

  section "Database Inventory"
  EXCLUDE_SQL="'$(echo "${DB_NAME_EXCLUDES}" | sed "s/,/','/g")'"
  DB_LIST_SQL="SELECT datname FROM pg_database WHERE datistemplate = false AND datallowconn = true AND datname NOT IN (${EXCLUDE_SQL}) ORDER BY datname;"
  DB_LIST="$(psql_db postgres "${DB_LIST_SQL}")"
  if [ -z "${DB_LIST}" ]; then
    echo "No application databases found or database container is unavailable."
  else
    printf '%s\n' "${DB_LIST}"
  fi

  section "Per-Database Critical Module State"
  for DB in ${DB_LIST}; do
    echo
    echo "-- ${DB}"
    if ! table_exists "${DB}" "ir_module_module"; then
      echo "ir_module_module not found; skipping module checks."
      continue
    fi
    psql_db "${DB}" "SELECT name || '=' || state FROM ir_module_module WHERE name IN ('base','web','crm','contacts','sale','account','hr_attendance','website','im_livechat','elsx_client_restrictions','elsx_saas','elsx_whatsapp_marketing','elsx_attendance_tracking','elsx_face_attendance','elsx_tally_integration','elsx_public_router') ORDER BY name;"
  done

  section "WhatsApp Isolation / Webhook Safety"
  for DB in ${DB_LIST}; do
    echo
    echo "-- ${DB}"
    if table_exists "${DB}" "whatsapp_account"; then
      psql_db "${DB}" "SELECT 'accounts=' || count(*) FROM whatsapp_account;"
      psql_db "${DB}" "SELECT 'primary_webhook=' || count(*) FROM whatsapp_account WHERE COALESCE(is_primary_webhook_db, false) = true;"
      psql_db "${DB}" "SELECT 'verified_or_connected=' || count(*) FROM whatsapp_account WHERE COALESCE(webhook_status, '') IN ('verified','connected') OR COALESCE(status, '') IN ('verified','connected');"
    else
      echo "whatsapp_account table not present."
    fi
  done

  section "SaaS Master Data Presence"
  SAAS_DB_CANDIDATES="${MASTER_DB:-${PRIMARY_CLIENT_DB}}"
  for DB in ${SAAS_DB_CANDIDATES}; do
    echo
    echo "-- ${DB}"
    if ! database_exists "${DB}"; then
      echo "Database not found."
      continue
    fi
    if table_exists "${DB}" "elsx_saas_tenant"; then
      psql_db "${DB}" "SELECT 'tenants=' || count(*) FROM elsx_saas_tenant;"
      psql_db "${DB}" "SELECT state || '=' || count(*) FROM elsx_saas_tenant GROUP BY state ORDER BY state;"
    else
      echo "elsx_saas_tenant table not present."
    fi
    if table_exists "${DB}" "elsx_saas_billing_plan"; then
      psql_db "${DB}" "SELECT 'billing_plans=' || count(*) FROM elsx_saas_billing_plan;"
    else
      echo "elsx_saas_billing_plan table not present."
    fi
  done

  section "Readiness Findings"
  echo "- Existing client protection: use deploy/safe_production_update.sh with one DB, not all DBs, unless explicitly required."
  echo "- Multi-tenant isolation gap: odoo.docker.conf currently leaves dbfilter/db_name disabled for DB manager flexibility."
  echo "- SaaS objective requires a controlled domain-to-db routing/dbfilter rollout before public multi-tenant use."
  echo "- WhatsApp current routing depends on per-webhook DB selection or primary DB flags; multi-tenant WABA routing must be designed per tenant before scaling."
  echo "- Sidecars are intentionally separate for realtime WhatsApp and optional face recognition; keep optional profiles disabled until approved."

  section "Safe Next Commands"
  echo "# Audit only:"
  echo "bash deploy/saas_readiness_audit.sh"
  echo
  echo "# Upgrade only the live client DB after encrypted backup:"
  echo "read -s -p \"Backup passphrase: \" BACKUP_PASSPHRASE && echo && export BACKUP_PASSPHRASE && TARGET_DBS=${PRIMARY_CLIENT_DB} CONFIRM_TARGET_DBS=YES bash deploy/safe_update_all_dbs.sh"
  echo
  echo "# Full all-DB update only when intentionally tenant-wide:"
  echo "read -s -p \"Backup passphrase: \" BACKUP_PASSPHRASE && echo && export BACKUP_PASSPHRASE && CONFIRM_ALL_DBS=YES bash deploy/safe_update_all_dbs.sh"

} | tee "${REPORT_FILE}"

echo
echo "Report saved to: ${REPORT_FILE}"
