#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${1:-${LIVE_DB_NAME:-}}"
INSTALL_MODULES="${INSTALL_MODULES:-}"
NO_PULL="${NO_PULL:-NO}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo
echo "FibraFRP production deploy"
echo "Mode: keep client data, update code, build/start containers"
echo "Module lock: update installed modules only unless INSTALL_MODULES is set"

if [ "${NO_PULL}" != "YES" ]; then
  echo
  echo "==> Pulling latest code"
  git pull --ff-only origin main
fi

if [ -n "${DB_NAME}" ]; then
  export ODOO_AUTO_UPDATE_DB_NAME="${DB_NAME}"
fi
if [ -n "${INSTALL_MODULES}" ]; then
  export ODOO_AUTO_INSTALL_MODULES="${INSTALL_MODULES}"
  export ODOO_AUTO_UPDATE_MODULES="all,${INSTALL_MODULES}"
  export ODOO_AUTO_ALLOW_INSTALL="YES"
fi

echo
echo "==> Building and starting app"
docker compose up -d --build
docker compose ps

echo
echo "Done. Odoo startup refreshes Apps and upgrades installed modules only."
