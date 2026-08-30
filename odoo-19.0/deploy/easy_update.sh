#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${1:-${LIVE_DB_NAME:-}}"
INSTALL_MODULES="${INSTALL_MODULES:-}"
UPGRADE_MODULES="${UPGRADE_MODULES:-all}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

echo "==> Checking addon folders and manifest dependencies"
python3 deploy/audit_addons_ready.py

echo "==> Ensuring PostgreSQL is running"
docker compose up -d db

if [ -z "${DB_NAME}" ]; then
  mapfile -t DATABASES < <(
    docker compose exec -T db psql -U "${POSTGRES_USER:-odoo}" -d postgres -Atc \
      "SELECT datname FROM pg_database WHERE datistemplate=false AND datallowconn=true AND datname NOT IN ('postgres') ORDER BY datname;"
  )
  if [ "${#DATABASES[@]}" -eq 0 ]; then
    echo "ERROR: no application databases found." >&2
    exit 1
  fi
  if [ "${#DATABASES[@]}" -eq 1 ]; then
    DB_NAME="${DATABASES[0]}"
    echo "==> Using database: ${DB_NAME}"
  else
    echo "Available databases:"
    select selected in "${DATABASES[@]}"; do
      if [ -n "${selected}" ]; then
        DB_NAME="${selected}"
        break
      fi
    done
  fi
fi

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  read -r -s -p "Backup password: " BACKUP_PASSPHRASE
  echo
  export BACKUP_PASSPHRASE
fi
if [ -z "${BACKUP_PASSPHRASE}" ]; then
  echo "ERROR: backup password cannot be empty." >&2
  exit 1
fi

if [ -n "${INSTALL_MODULES}" ]; then
  EXTRA_INSTALL_MODULES="${INSTALL_MODULES}" \
  EXTRA_UPGRADE_MODULES="${INSTALL_MODULES}" \
  UPGRADE_MODULES="${UPGRADE_MODULES}" \
    bash deploy/safe_production_update.sh "${DB_NAME}"
else
  UPGRADE_MODULES="${UPGRADE_MODULES}" bash deploy/safe_production_update.sh "${DB_NAME}"
fi

echo
echo "Done. Apps list and installed modules are updated for ${DB_NAME}."
