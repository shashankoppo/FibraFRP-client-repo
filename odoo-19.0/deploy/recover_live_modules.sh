#!/usr/bin/env bash
set -euo pipefail

LIVE_DB_NAME="${1:-${LIVE_DB_NAME:-FiberaFRP_DB}}"
CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
DB_USER="${POSTGRES_USER:-odoo}"

# Keep this list focused on the apps that disappear when Invoicing/WhatsApp
# are accidentally uninstalled. Operators can override it if they need more.
RECOVERY_MODULES="${RECOVERY_MODULES:-account,crm,contacts,sale,elsx_whatsapp_marketing,elsx_tally_integration,elsx_client_restrictions,elsx_attendance_tracking}"
UPGRADE_MODULES="${UPGRADE_MODULES:-elsx_client_restrictions,elsx_whatsapp_marketing,elsx_tally_integration,elsx_attendance_tracking}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

sql_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "${value}"
}

SAFE_DB_NAME="$(printf '%s' "${LIVE_DB_NAME}" | tr -c 'A-Za-z0-9_.-' '_')"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_DIR}/backups/recover_${SAFE_DB_NAME}_${TIMESTAMP}}"
LIVE_DB_SQL="$(sql_quote "${LIVE_DB_NAME}")"

echo "==> Production database: ${LIVE_DB_NAME}"
echo "==> Recovery modules: ${RECOVERY_MODULES}"
echo "==> Upgrade modules: ${UPGRADE_MODULES}"
echo "==> Backup directory: ${BACKUP_DIR}"
echo
echo "IMPORTANT: This script does not drop databases, delete Docker volumes, or"
echo "hard-reset live data. It first creates a database dump and filestore backup,"
echo "then reinstalls/upgrades the missing modules on ${LIVE_DB_NAME}."
echo

echo "==> Ensuring PostgreSQL is running"
docker compose up -d db

DB_EXISTS="$(
  docker compose exec -T db psql -U "${DB_USER}" -d postgres -Atc \
    "SELECT 1 FROM pg_database WHERE datname = ${LIVE_DB_SQL};"
)"

if [ "${DB_EXISTS}" != "1" ]; then
  echo "ERROR: Database ${LIVE_DB_NAME} does not exist." >&2
  echo "Check the database name in /web/database/manager, then rerun this script." >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

echo "==> Backing up PostgreSQL database ${LIVE_DB_NAME}"
docker compose exec -T db pg_dump -U "${DB_USER}" -d "${LIVE_DB_NAME}" \
  > "${BACKUP_DIR}/${SAFE_DB_NAME}.sql"

echo "==> Backing up filestore for ${LIVE_DB_NAME} if present"
if docker compose run --rm -T --no-deps -e LIVE_DB_NAME="${LIVE_DB_NAME}" odoo sh -c \
  'test -d "/root/.local/share/Odoo/filestore/${LIVE_DB_NAME}"'; then
  docker compose run --rm -T --no-deps -e LIVE_DB_NAME="${LIVE_DB_NAME}" odoo sh -c \
    'tar -C /root/.local/share/Odoo/filestore -czf - "${LIVE_DB_NAME}"' \
    > "${BACKUP_DIR}/${SAFE_DB_NAME}_filestore.tgz"
else
  echo "---- No filestore directory found for ${LIVE_DB_NAME}; continuing."
fi

echo "==> Current module state before recovery"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT name, state, latest_version
     FROM ir_module_module
    WHERE name IN (
      'account', 'crm', 'contacts', 'sale',
      'elsx_whatsapp_marketing', 'elsx_tally_integration',
      'elsx_client_restrictions', 'elsx_attendance_tracking'
    )
    ORDER BY name;"

echo "==> Stopping Odoo and sidecar for a clean module recovery"
docker compose stop sidecar >/dev/null 2>&1 || true
docker compose stop odoo >/dev/null 2>&1 || true

echo "==> Installing missing Invoicing/WhatsApp dependencies and upgrading custom modules"
docker compose run --rm -T --no-deps odoo \
  python3 /opt/odoo/odoo-bin \
    -c "${CONFIG}" \
    -d "${LIVE_DB_NAME}" \
    -i "${RECOVERY_MODULES}" \
    -u "${UPGRADE_MODULES}" \
    --stop-after-init

echo "==> Re-merging safe WhatsApp default data as inactive reviewable blueprints"
docker compose run --rm -T --no-deps odoo \
  python3 /opt/odoo/odoo-bin shell \
    -c "${CONFIG}" \
    -d "${LIVE_DB_NAME}" <<'PY'
params = env['ir.config_parameter'].sudo()
sample_model = env['whatsapp.sample.template'].sudo()
form_model = env['whatsapp.form'].sudo()

sample_model._seed_sample_templates()
form_model._seed_fiberafrp_production_forms()

accounts = env['whatsapp.account'].sudo().search([('active', '=', True)])
if not accounts:
    print("No active WhatsApp account found; sample templates and forms were re-merged.")
    print("After creating/recovering the account, click Initialize Defaults on the account form.")
else:
    if not params.get_param('whatsapp.default.account.id'):
        params.set_param('whatsapp.default.account.id', str(accounts[0].id))
    for account in accounts:
        ctx = dict(
            env.context,
            whatsapp_seed_account_id=account.id,
            restore_defaults_inactive=True,
        )
        env['whatsapp.sample.template'].with_context(ctx).sudo()._seed_sample_templates()
        env['whatsapp.form'].with_context(ctx).sudo()._seed_fiberafrp_production_forms()
        env['whatsapp.bot.flow'].with_context(ctx).sudo()._seed_fiberafrp_assistant_flow()
        env['whatsapp.bot.flow'].with_context(ctx).sudo()._seed_fiberafrp_advanced_business_flows()
    print("WhatsApp defaults re-merged for %s active account(s). Flow blueprints remain inactive unless already active." % len(accounts))
env.cr.commit()
PY

echo "==> Starting Odoo and WhatsApp sidecar"
docker compose up -d odoo sidecar

echo "==> Module state after recovery"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT name, state, latest_version
     FROM ir_module_module
    WHERE name IN (
      'account', 'crm', 'contacts', 'sale',
      'elsx_whatsapp_marketing', 'elsx_tally_integration',
      'elsx_client_restrictions', 'elsx_attendance_tracking'
    )
    ORDER BY name;"

echo "==> Key table check"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT to_regclass('public.account_move') AS account_move,
          to_regclass('public.whatsapp_account') AS whatsapp_account,
          to_regclass('public.whatsapp_chat') AS whatsapp_chat,
          to_regclass('public.whatsapp_message') AS whatsapp_message;"

echo "==> Recent Odoo errors, if any"
docker logs --since 2m odoo_app 2>&1 | grep -Ei \
  'ERROR|Traceback|CRITICAL|RPC_ERROR|OwlError|ParseError|Exception' || true

echo
echo "==> Recovery finished."
echo "Backup saved at: ${BACKUP_DIR}"
echo "Open ${LIVE_DB_NAME}, then check Invoicing, WhatsApp Marketing, Team Inbox,"
echo "Templates, Campaigns, and one test incoming WhatsApp message."
