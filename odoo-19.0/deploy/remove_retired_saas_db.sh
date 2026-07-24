#!/usr/bin/env bash
set -euo pipefail

# Internal migration helper. Callers must create and verify a backup first.
DATABASE="${1:?database name is required}"
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-odoo}"
DB_PASSWORD="${DB_PASSWORD:-}"
ODOO_CONFIG="${ODOO_RC:-${ODOO_CONFIG:-/etc/odoo/odoo.conf}}"
ODOO_BIN="${ODOO_BIN:-/opt/odoo/odoo-bin}"
LEGACY_ADDONS_PATH="${ELSX_LEGACY_ADDONS_PATH:-/opt/odoo/deploy/removal_capsules}"
ACTIVE_ADDONS_PATH="/opt/odoo/addons,/opt/odoo/odoo/addons,/opt/odoo/custom_addons"

psql_db() {
  PGPASSWORD="${DB_PASSWORD}" psql \
    -X -v ON_ERROR_STOP=1 \
    -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DATABASE}" \
    "$@"
}

state="$(
  psql_db -Atc \
    "SELECT state FROM ir_module_module WHERE name = 'elsx_saas' LIMIT 1;"
)"

case "${state}" in
  ''|uninstalled)
    printf '[saas-removal] %s: already absent or uninstalled.\n' "${DATABASE}" >&2
    exit 0
    ;;
  installed)
    ;;
  uninstallable)
    printf '[saas-removal] %s: restoring stale module state for cleanup.\n' "${DATABASE}" >&2
    psql_db -c \
      "UPDATE ir_module_module SET state = 'installed' WHERE name = 'elsx_saas' AND state = 'uninstallable';" \
      >/dev/null
    ;;
  *)
    printf '[saas-removal] %s: refusing unexpected module state %s.\n' "${DATABASE}" "${state}" >&2
    exit 1
    ;;
esac

printf '[saas-removal] %s: uninstalling retired module.\n' "${DATABASE}" >&2
python3 "${ODOO_BIN}" shell \
  -c "${ODOO_CONFIG}" \
  --addons-path="${LEGACY_ADDONS_PATH},${ACTIVE_ADDONS_PATH}" \
  --db_host="${DB_HOST}" \
  --db_port="${DB_PORT}" \
  --db_user="${DB_USER}" \
  --db_password="${DB_PASSWORD}" \
  -d "${DATABASE}" --no-http --log-level=error <<'PY'
module = env['ir.module.module'].search([('name', '=', 'elsx_saas')], limit=1)
if module and module.state == 'installed':
    env['ir.config_parameter'].sudo().set_param('elsx_saas.enabled', '0')
    module.with_context(elsx_apps_password_unlocked=True).button_immediate_uninstall()
    env.cr.commit()
PY

remaining="$(
  psql_db -Atc \
    "SELECT count(*) FROM ir_module_module WHERE name = 'elsx_saas' AND state != 'uninstalled';"
)"
if [ "${remaining}" != '0' ]; then
  printf '[saas-removal] %s: uninstall did not complete.\n' "${DATABASE}" >&2
  exit 1
fi

psql_db -c \
  "DELETE FROM ir_config_parameter WHERE key = 'elsx_saas.enabled' OR key LIKE 'elsx_saas.%';" \
  >/dev/null
printf '[saas-removal] %s: complete.\n' "${DATABASE}" >&2
