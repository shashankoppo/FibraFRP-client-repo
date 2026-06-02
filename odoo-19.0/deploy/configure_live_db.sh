#!/usr/bin/env bash
set -euo pipefail

LIVE_DB_NAME="${1:-${LIVE_DB_NAME:-FiberaFRP_DB}}"
LIVE_ACCOUNT_ID="${2:-${WHATSAPP_ACCOUNT_ID:-}}"
LIVE_VERIFY_TOKEN="${3:-${WHATSAPP_VERIFY_TOKEN:-}}"
MODULES="${MODULES:-elsx_client_restrictions,elsx_whatsapp_marketing,elsx_attendance_tracking,elsx_tally_integration}"
INSTALL_MODULES="${INSTALL_MODULES:-elsx_client_restrictions,elsx_whatsapp_marketing,elsx_attendance_tracking,elsx_tally_integration}"
CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
DB_USER="${POSTGRES_USER:-odoo}"

sql_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "${value}"
}

LIVE_DB_SQL="$(sql_quote "${LIVE_DB_NAME}")"

echo "==> Production database: ${LIVE_DB_NAME}"
if [ -n "${LIVE_ACCOUNT_ID}" ]; then
  if ! [[ "${LIVE_ACCOUNT_ID}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: WhatsApp account ID must be numeric: ${LIVE_ACCOUNT_ID}" >&2
    exit 1
  fi
  echo "==> Requested primary WhatsApp account ID: ${LIVE_ACCOUNT_ID}"
fi
if [ -n "${LIVE_VERIFY_TOKEN}" ]; then
  echo "==> Requested webhook verify token: $(printf '%s' "${LIVE_VERIFY_TOKEN}" | sed -E 's/^(.{3}).*(.{3})$/\1...\2/')"
fi
echo "==> Modules to upgrade: ${MODULES}"
if [ -n "${INSTALL_MODULES}" ]; then
  echo "==> Modules to install if missing: ${INSTALL_MODULES}"
fi

echo "==> Ensuring PostgreSQL is running"
docker compose up -d db

DB_EXISTS="$(
  docker compose exec -T db psql -U "${DB_USER}" -d postgres -Atc \
    "SELECT 1 FROM pg_database WHERE datname = ${LIVE_DB_SQL};"
)"

if [ "${DB_EXISTS}" != "1" ]; then
  echo "ERROR: Database ${LIVE_DB_NAME} does not exist." >&2
  echo "Create/restore it first from /web/database/manager, then rerun this script." >&2
  exit 1
fi

echo "==> Stopping Odoo and sidecar for a clean module upgrade"
docker compose stop sidecar >/dev/null 2>&1 || true
docker compose stop odoo >/dev/null 2>&1 || true

echo "==> Repairing stale ELSxGlobal branding view if present"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
DECLARE
  parent_view_id integer;
  target_view_id integer;
  updated_count integer;
  safe_arch text := $body$<data>
    <xpath expr="//t[@t-out]" position="replace">
        <span>Powered by <span>ELSxGlobal</span></span>
    </xpath>
</data>$body$;
BEGIN
  IF to_regclass('public.ir_ui_view') IS NULL
     OR to_regclass('public.ir_model_data') IS NULL THEN
    RAISE NOTICE 'Base view tables are not present; skipping branding rescue.';
    RETURN;
  END IF;

  SELECT res_id
    INTO parent_view_id
    FROM ir_model_data
   WHERE module = 'web'
     AND name = 'brand_promotion'
     AND model = 'ir.ui.view'
   LIMIT 1;

  SELECT res_id
    INTO target_view_id
    FROM ir_model_data
   WHERE module = 'web'
     AND name = 'brand_promotion_message'
     AND model = 'ir.ui.view'
   LIMIT 1;

  IF target_view_id IS NULL THEN
    RAISE NOTICE 'Target brand promotion message template is missing; skipping branding rescue.';
    RETURN;
  END IF;

  UPDATE ir_ui_view AS v
     SET name = 'ELSxGlobal Brand Promotion Message',
         inherit_id = target_view_id,
         arch_db = jsonb_build_object('en_US', safe_arch),
         arch_prev = NULL,
         arch_updated = false
   WHERE (
       EXISTS (
         SELECT 1
           FROM ir_model_data d
          WHERE d.model = 'ir.ui.view'
            AND d.res_id = v.id
            AND d.module = 'elsx_client_restrictions'
            AND d.name = 'elsx_brand_promotion'
       )
       OR (
         parent_view_id IS NOT NULL
         AND v.inherit_id = parent_view_id
         AND (
             lower(v.name) LIKE '%elsx%'
             OR lower(COALESCE(v.arch_db::text, '')) LIKE '%elsxglobal%'
             OR COALESCE(v.arch_db::text, '') LIKE '%o_brand_promotion%'
         )
         AND NOT EXISTS (
           SELECT 1
             FROM ir_model_data d
            WHERE d.model = 'ir.ui.view'
              AND d.res_id = v.id
              AND d.module IN ('web', 'website')
         )
       )
     )
     AND (
         v.inherit_id IS DISTINCT FROM target_view_id
         OR COALESCE(v.arch_db::text, '') LIKE '%o_brand_promotion%'
         OR COALESCE(v.arch_db::text, '') LIKE '%web.brand_promotion%'
     );
  GET DIAGNOSTICS updated_count = ROW_COUNT;

  RAISE NOTICE 'Branding rescue updated % view(s).', updated_count;
END $$;
SQL

echo "==> Normalizing PostgreSQL-safe timezone values"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
DECLARE
  updated_count integer := 0;
BEGIN
  IF to_regclass('public.res_partner') IS NOT NULL THEN
    UPDATE res_partner SET tz = 'Asia/Kolkata' WHERE tz = 'Asia/Calcutta';
    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RAISE NOTICE 'Timezone rescue updated % res_partner row(s).', updated_count;
  END IF;

  IF to_regclass('public.resource_calendar') IS NOT NULL THEN
    UPDATE resource_calendar SET tz = 'Asia/Kolkata' WHERE tz = 'Asia/Calcutta';
    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RAISE NOTICE 'Timezone rescue updated % resource_calendar row(s).', updated_count;
  END IF;

  IF to_regclass('public.resource_resource') IS NOT NULL THEN
    UPDATE resource_resource SET tz = 'Asia/Kolkata' WHERE tz = 'Asia/Calcutta';
    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RAISE NOTICE 'Timezone rescue updated % resource_resource row(s).', updated_count;
  END IF;

  IF to_regclass('public.whatsapp_scheduled_message') IS NOT NULL THEN
    UPDATE whatsapp_scheduled_message SET timezone_id = 'Asia/Kolkata' WHERE timezone_id = 'Asia/Calcutta';
    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RAISE NOTICE 'Timezone rescue updated % whatsapp_scheduled_message row(s).', updated_count;
  END IF;

  IF to_regclass('public.whatsapp_scheduled_campaign') IS NOT NULL THEN
    UPDATE whatsapp_scheduled_campaign SET timezone_id = 'Asia/Kolkata' WHERE timezone_id = 'Asia/Calcutta';
    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RAISE NOTICE 'Timezone rescue updated % whatsapp_scheduled_campaign row(s).', updated_count;
  END IF;
END $$;
SQL

echo "==> Installing/upgrading live database modules"
ODOO_MODULE_ARGS=()
if [ -n "${INSTALL_MODULES}" ]; then
  ODOO_MODULE_ARGS+=("-i" "${INSTALL_MODULES}")
fi
ODOO_MODULE_ARGS+=("-u" "${MODULES}")

docker compose run --rm -T --no-deps odoo \
  python3 /opt/odoo/odoo-bin \
    -c "${CONFIG}" \
    -d "${LIVE_DB_NAME}" \
    "${ODOO_MODULE_ARGS[@]}" \
    --stop-after-init

echo "==> Re-merging safe WhatsApp forms/templates/flow blueprints"
docker compose run --rm -T --no-deps odoo \
  python3 /opt/odoo/odoo-bin shell \
    -c "${CONFIG}" \
    -d "${LIVE_DB_NAME}" <<'PY'
params = env['ir.config_parameter'].sudo()
if 'whatsapp.account' not in env.registry.models:
    print("WhatsApp module is not available after install/upgrade; skipping default merge.")
else:
    env['whatsapp.sample.template'].sudo()._seed_sample_templates()
    env['whatsapp.form'].sudo()._seed_fiberafrp_production_forms()
    accounts = env['whatsapp.account'].sudo().search([('active', '=', True)])
    if not accounts:
        print("No active WhatsApp account found. Create/recover the account, then click Initialize Defaults.")
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
        print("Defaults re-merged for %s active WhatsApp account(s). Blueprints stay inactive unless already active." % len(accounts))
    env.cr.commit()
PY

echo "==> Marking ${LIVE_DB_NAME} as the primary WhatsApp webhook database"
mapfile -t DATABASES < <(
  docker compose exec -T db psql -U "${DB_USER}" -d postgres -Atc \
    "SELECT datname
       FROM pg_database
      WHERE datistemplate = false
        AND datallowconn = true
        AND datname <> 'postgres'
      ORDER BY datname;"
)

for DB in "${DATABASES[@]}"; do
  TABLE_EXISTS="$(
    docker compose exec -T db psql -U "${DB_USER}" -d "${DB}" -Atc \
      "SELECT to_regclass('public.whatsapp_account') IS NOT NULL;"
  )"
  if [ "${TABLE_EXISTS}" != "t" ]; then
    echo "---- ${DB}: whatsapp_account table not present; skipping webhook flag"
    continue
  fi

  if [ "${DB}" = "${LIVE_DB_NAME}" ]; then
    if [ -n "${LIVE_ACCOUNT_ID}" ]; then
      PRIMARY_ACCOUNT_ID="$(
        docker compose exec -T db psql -U "${DB_USER}" -d "${DB}" -Atc \
          "SELECT id
             FROM whatsapp_account
            WHERE active = true
              AND id = ${LIVE_ACCOUNT_ID}
            LIMIT 1;"
      )"
    else
      PRIMARY_ACCOUNT_ID="$(
        docker compose exec -T db psql -U "${DB_USER}" -d "${DB}" -Atc \
          "SELECT id
             FROM whatsapp_account
            WHERE active = true
            ORDER BY (webhook_status = 'verified') DESC,
                     (status = 'connected') DESC,
                     id ASC
            LIMIT 1;"
      )"
    fi

    if [ -z "${PRIMARY_ACCOUNT_ID}" ]; then
      echo "---- ${DB}: no active WhatsApp account found; skipping primary webhook flag" >&2
      continue
    fi

    docker compose exec -T db psql -U "${DB_USER}" -d "${DB}" -c \
      "UPDATE whatsapp_account
          SET is_primary_webhook_db = (id = ${PRIMARY_ACCOUNT_ID});" >/dev/null
    if [ -n "${LIVE_VERIFY_TOKEN}" ]; then
      LIVE_VERIFY_TOKEN_SQL="$(sql_quote "${LIVE_VERIFY_TOKEN}")"
      docker compose exec -T db psql -U "${DB_USER}" -d "${DB}" -c \
        "UPDATE whatsapp_account
            SET webhook_verify_token = ${LIVE_VERIFY_TOKEN_SQL}
          WHERE id = ${PRIMARY_ACCOUNT_ID};" >/dev/null
      echo "---- ${DB}: webhook verify token updated on WhatsApp account ${PRIMARY_ACCOUNT_ID}"
    fi
    echo "---- ${DB}: WhatsApp account ${PRIMARY_ACCOUNT_ID} marked primary; others disabled"
  else
    docker compose exec -T db psql -U "${DB_USER}" -d "${DB}" -c \
      "UPDATE whatsapp_account
          SET is_primary_webhook_db = false;" >/dev/null
    echo "---- ${DB}: WhatsApp webhook primary flag disabled"
  fi
done

echo "==> Live WhatsApp account status"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT id,
          name,
          phone_number,
          status,
          webhook_status,
          is_primary_webhook_db,
          CASE
            WHEN webhook_verify_token IS NULL OR webhook_verify_token = '' THEN ''
            WHEN length(webhook_verify_token) <= 8 THEN '***'
            ELSE left(webhook_verify_token, 3) || '...' || right(webhook_verify_token, 3)
          END AS verify_token_hint
     FROM whatsapp_account
    ORDER BY id;"

echo "==> Starting Odoo and sidecar"
docker compose up -d odoo sidecar

echo "==> Done."
echo "Use this Meta webhook callback URL:"
echo "    https://YOUR_DOMAIN/whatsapp/webhook?db=${LIVE_DB_NAME}"
if [ -n "${LIVE_VERIFY_TOKEN}" ]; then
  echo "Use this Meta verify token:"
  echo "    ${LIVE_VERIFY_TOKEN}"
  echo "Test verification from the server with:"
  echo "    curl -i \"https://YOUR_DOMAIN/whatsapp/webhook?db=${LIVE_DB_NAME}&hub.mode=subscribe&hub.verify_token=${LIVE_VERIFY_TOKEN}&hub.challenge=12345\""
fi
echo "Then verify logs with:"
echo "    docker logs --tail 200 odoo_app"
echo "    docker logs --tail 100 whatsapp_sidecar"
