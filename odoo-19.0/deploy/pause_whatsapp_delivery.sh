#!/usr/bin/env bash
set -euo pipefail

LIVE_DB_NAME="${1:-${LIVE_DB_NAME:-FiberaFRP_DB}}"
DB_USER="${POSTGRES_USER:-odoo}"

echo "==> Waiting for any active WhatsApp worker transaction, then pausing all delivery crons"
docker compose up -d db >/dev/null
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "UPDATE ir_cron AS cron
      SET active = FALSE
     FROM ir_act_server AS action,
          ir_model AS model
    WHERE cron.ir_actions_server_id = action.id
      AND action.model_id = model.id
      AND (
        (model.model = 'whatsapp.campaign' AND action.code = 'model._cron_process_global_queue()')
        OR (model.model = 'whatsapp.message' AND action.code IN (
          'model._cron_process_broadcast_queue()',
          'model._cron_retry_failed()'
        ))
        OR (model.model = 'whatsapp.scheduled.campaign' AND action.code = 'model._cron_process_scheduled_campaigns()')
        OR (model.model = 'whatsapp.campaign.participant' AND action.code = 'model.process_drip_campaigns()')
      );"

echo "==> WhatsApp delivery crons are paused. Webhooks and inbox reception remain active."
echo "==> A module upgrade re-enables healthy workers after orphaned rows are quarantined."
