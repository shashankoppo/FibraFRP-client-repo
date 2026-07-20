#!/usr/bin/env bash
set -euo pipefail

LIVE_DB_NAME="${1:-${LIVE_DB_NAME:-}}"

if [ -z "${LIVE_DB_NAME}" ]; then
  echo "ERROR: database name is required. The WhatsApp bridge never guesses a database." >&2
  echo "Usage: BACKUP_PASSPHRASE=... bash deploy/upgrade_whatsapp_bridge.sh <database_name>" >&2
  exit 2
fi

append_modules() {
  local current="${1:-}"
  local required="${2}"
  if [ -n "${current}" ]; then
    printf '%s,%s' "${current}" "${required}"
  else
    printf '%s' "${required}"
  fi
}

# Keep this bridge focused. Callers can still extend the lists explicitly.
export INSTALL_MODULES="${INSTALL_MODULES:-elsx_client_restrictions}"
export UPGRADE_MODULES="${UPGRADE_MODULES:-elsx_client_restrictions}"
export EXTRA_INSTALL_MODULES="$(append_modules "${EXTRA_INSTALL_MODULES:-}" 'elsx_ai_core,elsx_whatsapp_core,elsx_whatsapp_gateway')"
export EXTRA_UPGRADE_MODULES="$(append_modules "${EXTRA_UPGRADE_MODULES:-}" 'elsx_ai_core,elsx_whatsapp_core,elsx_whatsapp_gateway,elsx_whatsapp_marketing,elsx_ai_marketing,elsx_ai_website_builder')"
export DEACTIVATE_SAAS_ON_UPDATE="${DEACTIVATE_SAAS_ON_UPDATE:-NO}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/safe_production_update.sh" "${LIVE_DB_NAME}"
