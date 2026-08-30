#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${1:-${NEW_DB_NAME:-}}"
COUNTRY="${2:-${COUNTRY:-IN}}"
ADMIN_LOGIN="${ADMIN_LOGIN:-admin}"
NO_PULL="${NO_PULL:-NO}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [ -z "${DB_NAME}" ]; then
  echo "Usage: bash deploy-new.sh <db_name> [country]"
  exit 2
fi

echo
echo "FibraFRP new client deploy"
echo "Mode: create fresh database, install CE/custom modules, start app"

if [ "${NO_PULL}" != "YES" ]; then
  echo
  echo "==> Pulling latest code"
  git pull --ff-only origin main
fi

echo
echo "==> Checking addon folders and dependencies"
python3 deploy/audit_addons_ready.py

if [ -z "${NEW_DB_ADMIN_PASSWORD:-}" ]; then
  read -r -s -p "New admin password: " NEW_DB_ADMIN_PASSWORD
  echo
  export NEW_DB_ADMIN_PASSWORD
fi

CONFIRM_CREATE_DB=YES bash deploy/create_client_database.sh "${DB_NAME}" "${COUNTRY}" "${ADMIN_LOGIN}"
