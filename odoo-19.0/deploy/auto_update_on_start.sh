#!/usr/bin/env bash
set -euo pipefail
if [ "${ODOO_AUTO_UPDATE_ON_START:-NO}" = "YES" ]; then
  echo "ERROR: startup upgrades are retired. Use bash deploy-prod.sh." >&2
  exit 1
fi
echo "[auto-update] Disabled. Schema updates use the guarded deployment runner."
python3 /opt/odoo/deploy/startup_guard.py
