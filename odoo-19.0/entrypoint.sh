#!/bin/bash
set -e

# Wait for database. DB_PASSWORD from .env is passed to Odoo below and
# overrides odoo.conf so direct odoo-bin invocations use the same credentials.
until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}"; do
  echo "Waiting for database (${DB_HOST}:${DB_PORT})..."
  sleep 2
done

case " $* " in
  *" odoo-bin "*|*"/odoo-bin "*)
    bash /opt/odoo/deploy/restore_native_admin_on_start.sh
    ;;
esac

echo "Starting Odoo..."
exec "$@" -c "${ODOO_RC}" \
  --db_host="${DB_HOST}" \
  --db_port="${DB_PORT}" \
  --db_user="${DB_USER}" \
  --db_password="${DB_PASSWORD}"