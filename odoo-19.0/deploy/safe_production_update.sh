#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [ "$#" -gt 0 ]; then
  echo "Database arguments are retired. Configure ODOO_AUTO_UPDATE_DB_NAME on this VPS." >&2
  exit 2
fi
exec python3 deploy/client_deploy.py production
