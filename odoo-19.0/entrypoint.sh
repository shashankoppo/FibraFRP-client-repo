#!/bin/bash
set -e

# Wait for database. DB_PASSWORD from .env is passed to Odoo below and
# overrides odoo.conf so direct odoo-bin invocations use the same credentials.
until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}"; do
  echo "Waiting for database (${DB_HOST}:${DB_PORT})..."
  sleep 2
done

ODOO_EFFECTIVE_ADDONS_PATH="${ODOO_ADDONS_PATH:-/opt/odoo/addons,/opt/odoo/odoo/addons,/opt/odoo/custom_addons,/opt/odoo/custom_addons/elsx_stubs,/opt/odoo/third_party_addons}"
if [ -n "${ODOO_EXTRA_ADDONS_PATH:-}" ]; then
  ODOO_EFFECTIVE_ADDONS_PATH="${ODOO_EFFECTIVE_ADDONS_PATH},${ODOO_EXTRA_ADDONS_PATH}"
fi
export ODOO_EFFECTIVE_ADDONS_PATH

case " $* " in
  *" odoo-bin "*|*"/odoo-bin "*)
    bash /opt/odoo/deploy/restore_native_admin_on_start.sh
    case " $* " in
      *" --stop-after-init "*|*" shell "*|*" db "*)
        ;;
      *)
        bash /opt/odoo/deploy/auto_update_on_start.sh
        ;;
    esac
    ;;
esac

echo "Starting Odoo..."
exec "$@" -c "${ODOO_RC}" \
  --addons-path="${ODOO_EFFECTIVE_ADDONS_PATH}" \
  --db_host="${DB_HOST}" \
  --db_port="${DB_PORT}" \
  --db_user="${DB_USER}" \
  --db_password="${DB_PASSWORD}"
