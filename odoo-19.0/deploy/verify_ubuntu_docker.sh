#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== FiberaFRP Ubuntu 24.04 Docker verification =="

echo "-- Docker versions"
docker --version
docker compose version

echo "-- Compose config"
docker compose config >/tmp/fiberafrp-compose-config.yml
echo "Compose config OK"

echo "-- Service status"
docker compose ps

echo "-- Odoo health"
if curl -fsS http://127.0.0.1:8069/web/health >/dev/null; then
  echo "Odoo health OK"
else
  echo "Odoo health FAILED"
  exit 1
fi

echo "-- Database manager"
if curl -fsS http://127.0.0.1:8069/web/database/manager >/dev/null; then
  echo "Database manager reachable"
else
  echo "Database manager FAILED"
  exit 1
fi

echo "-- Sidecar health"
if curl -fsS http://127.0.0.1:3000/health >/dev/null; then
  echo "Sidecar health OK"
else
  echo "Sidecar health FAILED"
  exit 1
fi

echo "-- Recent critical logs"
if docker logs --since 10m odoo_app 2>&1 | grep -Ei "ERROR|Traceback|CRITICAL|RPC_ERROR|OwlError|ParseError" >/tmp/fiberafrp-odoo-critical.log; then
  echo "Recent Odoo critical log entries found:"
  cat /tmp/fiberafrp-odoo-critical.log
  exit 1
else
  echo "No recent Odoo critical log entries"
fi

if docker logs --since 10m whatsapp_sidecar 2>&1 | grep -Ei "ERROR|Traceback|CRITICAL|Unhandled|ECONNREFUSED" >/tmp/fiberafrp-sidecar-critical.log; then
  echo "Recent sidecar critical log entries found:"
  cat /tmp/fiberafrp-sidecar-critical.log
  exit 1
else
  echo "No recent sidecar critical log entries"
fi

echo "Verification complete"
