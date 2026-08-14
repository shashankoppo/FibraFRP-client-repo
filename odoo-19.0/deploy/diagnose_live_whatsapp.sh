#!/usr/bin/env bash
set -euo pipefail

LIVE_DB_NAME="${1:-${LIVE_DB_NAME:-FiberaFRP_DB}}"
CAMPAIGN_ID="${2:-}"
DB_USER="${POSTGRES_USER:-odoo}"

if [ -n "${CAMPAIGN_ID}" ] && ! [[ "${CAMPAIGN_ID}" =~ ^[0-9]+$ ]]; then
  echo "ERROR: Campaign ID must be numeric." >&2
  exit 1
fi

sql_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "${value}"
}

LIVE_DB_SQL="$(sql_quote "${LIVE_DB_NAME}")"

echo "==> WhatsApp diagnostics for database: ${LIVE_DB_NAME}"
docker compose up -d db >/dev/null

DB_EXISTS="$(
  docker compose exec -T db psql -U "${DB_USER}" -d postgres -Atc \
    "SELECT 1 FROM pg_database WHERE datname = ${LIVE_DB_SQL};"
)"

if [ "${DB_EXISTS}" != "1" ]; then
  echo "ERROR: Database ${LIVE_DB_NAME} does not exist." >&2
  exit 1
fi

echo
echo "==> Module state"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT name, state, latest_version
     FROM ir_module_module
    WHERE name IN (
      'account', 'crm', 'contacts', 'sale',
      'elsx_whatsapp_marketing', 'elsx_tally_integration',
      'elsx_client_restrictions', 'elsx_attendance_tracking'
    )
    ORDER BY name;"

echo
echo "==> Key tables"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT to_regclass('public.whatsapp_account') AS whatsapp_account,
          to_regclass('public.whatsapp_chat') AS whatsapp_chat,
          to_regclass('public.whatsapp_message') AS whatsapp_message,
          to_regclass('public.whatsapp_template') AS whatsapp_template,
          to_regclass('public.whatsapp_bot_flow') AS whatsapp_bot_flow,
          to_regclass('public.whatsapp_webhook_log') AS whatsapp_webhook_log;"

ACCOUNT_TABLE="$(
  docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -Atc \
    "SELECT to_regclass('public.whatsapp_account') IS NOT NULL;"
)"

if [ "${ACCOUNT_TABLE}" != "t" ]; then
  echo
  echo "WhatsApp account table is missing. Run module recovery/install first."
  exit 0
fi

echo
echo "==> WhatsApp accounts"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT id,
          name,
          phone_number,
          phone_number_id,
          active,
          status,
          webhook_status,
          is_primary_webhook_db,
          (access_token IS NOT NULL AND access_token <> '') AS has_access_token,
          (app_secret IS NOT NULL AND app_secret <> '') AS has_app_secret,
          skip_webhook_hmac,
          CASE
            WHEN webhook_verify_token IS NULL OR webhook_verify_token = '' THEN ''
            WHEN length(webhook_verify_token) <= 8 THEN '***'
            ELSE left(webhook_verify_token, 3) || '...' || right(webhook_verify_token, 3)
          END AS verify_token_hint,
          last_webhook_at,
          last_inbound_webhook_at,
          last_status_webhook_at,
          left(coalesce(webhook_last_error, ''), 180) AS webhook_last_error
     FROM whatsapp_account
    ORDER BY id;"

echo
echo "==> Counts"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT 'accounts' AS item, count(*) FROM whatsapp_account
    UNION ALL SELECT 'chats', count(*) FROM whatsapp_chat
    UNION ALL SELECT 'messages', count(*) FROM whatsapp_message
    UNION ALL SELECT 'templates', count(*) FROM whatsapp_template
    UNION ALL SELECT 'flows', count(*) FROM whatsapp_bot_flow
    UNION ALL SELECT 'webhook_logs', count(*) FROM whatsapp_webhook_log;"

PROVENANCE_COLUMN="$(
  docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -Atc \
    "SELECT EXISTS (
       SELECT 1
         FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'whatsapp_message'
          AND column_name = 'is_campaign_message'
     );"
)"

echo
echo "==> Detached campaign queue safety"
if [ "${PROVENANCE_COLUMN}" = "t" ]; then
  docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
    "SELECT status,
            count(*) AS messages,
            count(*) FILTER (WHERE next_retry_at IS NOT NULL) AS retry_scheduled,
            min(create_date) AS oldest,
            max(create_date) AS newest
       FROM whatsapp_message
      WHERE direction = 'outbound'
        AND campaign_id IS NULL
        AND is_campaign_message IS TRUE
      GROUP BY status
      ORDER BY status;"
else
  echo "Campaign provenance fields are missing; upgrade elsx_whatsapp_marketing before resuming delivery."
  docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
    "SELECT status, count(*) AS legacy_detached_candidates
       FROM whatsapp_message
      WHERE direction = 'outbound'
        AND campaign_id IS NULL
        AND chat_id_ref IS NULL
      GROUP BY status
      ORDER BY status;"
fi

echo
echo "==> PostgreSQL connection usage"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT datname, usename, state, count(*) AS connections
     FROM pg_stat_activity
    WHERE datname = ${LIVE_DB_SQL}
    GROUP BY datname, usename, state
    ORDER BY connections DESC;"

echo
echo "==> Recent and active campaigns"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT campaign.id,
          campaign.name,
          campaign.state,
          campaign.last_batch_at,
          count(message.id) FILTER (WHERE message.status = 'queued') AS queued,
          count(message.id) FILTER (WHERE message.status = 'failed') AS failed,
          count(message.id) FILTER (WHERE message.status IN ('sent', 'delivered', 'read')) AS accepted
     FROM whatsapp_campaign campaign
     LEFT JOIN whatsapp_message message
       ON message.campaign_id = campaign.id
      AND message.direction = 'outbound'
    WHERE campaign.state IN ('scheduled', 'running')
       OR campaign.id IN (SELECT id FROM whatsapp_campaign ORDER BY id DESC LIMIT 10)
    GROUP BY campaign.id, campaign.name, campaign.state, campaign.last_batch_at
    ORDER BY campaign.id DESC;"

echo
echo "==> WhatsApp delivery workers"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT model.model,
          action.code,
          cron.active,
          cron.lastcall,
          cron.nextcall,
          cron.failure_count
     FROM ir_cron cron
     JOIN ir_act_server action ON action.id = cron.ir_actions_server_id
     JOIN ir_model model ON model.id = action.model_id
    WHERE (model.model = 'whatsapp.campaign' AND action.code IN (
             'model._cron_process_global_queue()',
             'model._cron_evaluate_ab_tests()'
          ))
       OR (model.model = 'whatsapp.message' AND action.code IN (
             'model._cron_process_broadcast_queue()',
             'model._cron_retry_failed()'
          ))
       OR (model.model = 'whatsapp.scheduled.campaign' AND action.code = 'model._cron_process_scheduled_campaigns()')
       OR (model.model = 'whatsapp.campaign.participant' AND action.code = 'model.process_drip_campaigns()')
       OR (model.model = 'whatsapp.webhook.log' AND action.code = 'model._cron_recover_received()')
    ORDER BY model.model, action.code;"

if [ -n "${CAMPAIGN_ID}" ]; then
  echo
  echo "==> Campaign ${CAMPAIGN_ID}"
  docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
    "SELECT id,
            name,
            state,
            schedule_type,
            schedule_date,
            last_batch_at,
            preflight_state,
            preflight_checked_at,
            audience_source_count,
            audience_unique_count,
            audience_duplicate_count,
            audience_invalid_phone_count
       FROM whatsapp_campaign
      WHERE id = ${CAMPAIGN_ID};"

  echo
  echo "==> Campaign ${CAMPAIGN_ID} message queue"
  docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
    "SELECT status,
            count(*) AS messages,
            count(*) FILTER (WHERE next_retry_at IS NOT NULL) AS retry_scheduled,
            min(create_date) AS oldest,
            max(write_date) AS latest_change
       FROM whatsapp_message
      WHERE campaign_id = ${CAMPAIGN_ID}
        AND direction = 'outbound'
      GROUP BY status
      ORDER BY status;"

  echo
  echo "==> Campaign ${CAMPAIGN_ID} schedules"
  docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
    "SELECT id, status, schedule_type, scheduled_date, next_execution_date, execution_count
       FROM whatsapp_scheduled_campaign
      WHERE campaign_id = ${CAMPAIGN_ID}
      ORDER BY id DESC;"
fi

echo
echo "==> Flow status"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT id, name, account_id, active, trigger_type, keywords
     FROM whatsapp_bot_flow
    ORDER BY active DESC, id
    LIMIT 30;"

echo
echo "==> Template media readiness"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "WITH template_media AS (
      SELECT t.id,
             t.status,
             t.header_type,
             COALESCE(t.header_media_url, '') AS header_media_url,
             EXISTS (
               SELECT 1
                 FROM ir_attachment a
                WHERE a.res_model = 'whatsapp.template'
                  AND a.res_id = t.id
                  AND a.res_field = 'header_media_file'
                  AND COALESCE(a.store_fname, '') <> ''
             ) AS has_header_media_file
        FROM whatsapp_template t
    )
    SELECT status,
           header_type,
           count(*) AS total,
           count(*) FILTER (
             WHERE header_type IN ('image', 'video', 'document')
               AND header_media_url = ''
               AND NOT has_header_media_file
           ) AS missing_header_media
      FROM template_media
     GROUP BY status, header_type
     ORDER BY status, header_type;"

echo
echo "==> Recent webhook logs"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT id, create_date, event_type, status, account_id, left(coalesce(error_detail, ''), 180) AS error
     FROM whatsapp_webhook_log
    ORDER BY id DESC
    LIMIT 20;"

echo
echo "==> Recent Odoo/sidecar errors"
docker logs --since 30m odoo_app 2>&1 | grep -Ei \
  'WH-|webhook|ERROR|Traceback|CRITICAL|RPC_ERROR|OwlError|ParseError|Exception|Invalid Operation' || true
docker logs --since 30m whatsapp_sidecar 2>&1 | grep -Ei \
  'ERROR|Traceback|CRITICAL|Exception|Unhandled|ECONN|webhook|socket' || true

echo
echo "==> Sidecar health"
if ! docker compose exec -T sidecar wget -q -O - http://127.0.0.1:3000/health; then
  echo "ERROR: WhatsApp sidecar health check failed." >&2
  exit 1
fi

echo
echo "==> Diagnostic complete."
