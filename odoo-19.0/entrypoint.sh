#!/bin/bash
set -e

# ── Wait for database ─────────────────────────────────────────────────────────
# The DB_PASSWORD from .env is passed to Odoo via --db_password below,
# which always overrides the value in odoo.conf. The conf file is also kept
# in sync manually (odoo.docker.conf) so direct odoo-bin invocations work too.
until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}"; do
  echo "Waiting for database (${DB_HOST}:${DB_PORT})..."
  sleep 2
done

# ── Start Odoo ────────────────────────────────────────────────────────────────
echo "Starting Odoo..."
exec "$@" -c "${ODOO_RC}" \
  --db_host="${DB_HOST}" \
  --db_port="${DB_PORT}" \
  --db_user="${DB_USER}" \
  --db_password="${DB_PASSWORD}"
