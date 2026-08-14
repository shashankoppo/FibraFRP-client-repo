#!/usr/bin/env bash
set -euo pipefail

LIVE_DB_NAME="${1:-${LIVE_DB_NAME:-FiberaFRP_DB}}"
SOURCE_CAMPAIGN_ID="${2:-}"
WINDOW_MINUTES="${RECOVERY_WINDOW_MINUTES:-15}"
EXPECTED_MESSAGES="${EXPECTED_MESSAGES:-0}"
PENDING_ACTION="${RECOVERY_PENDING_ACTION:-cancel}"
CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
APPLY_RECOVERY="false"
RESTART_SERVICES="false"

if ! [[ "${SOURCE_CAMPAIGN_ID}" =~ ^[0-9]+$ ]]; then
  echo "Usage: bash deploy/recover_deleted_whatsapp_campaign.sh DATABASE REFERENCE_CAMPAIGN_ID" >&2
  exit 1
fi
if ! [[ "${WINDOW_MINUTES}" =~ ^[0-9]+$ ]] || [ "${WINDOW_MINUTES}" -lt 1 ]; then
  echo "ERROR: RECOVERY_WINDOW_MINUTES must be a positive integer." >&2
  exit 1
fi
if ! [[ "${EXPECTED_MESSAGES}" =~ ^[0-9]+$ ]]; then
  echo "ERROR: EXPECTED_MESSAGES must be zero or a positive integer." >&2
  exit 1
fi
if [ "${PENDING_ACTION}" != "cancel" ] && [ "${PENDING_ACTION}" != "resume" ]; then
  echo "ERROR: RECOVERY_PENDING_ACTION must be cancel or resume." >&2
  exit 1
fi
if [ "${CONFIRM_RECOVERY:-NO}" = "YES" ]; then
  APPLY_RECOVERY="true"
fi

restart_services() {
  if [ "${RESTART_SERVICES}" = "true" ]; then
    echo "==> Starting Odoo and WhatsApp sidecar"
    docker compose up -d odoo sidecar
  fi
}
trap restart_services EXIT

docker compose up -d db >/dev/null

if [ "${APPLY_RECOVERY}" = "true" ]; then
  echo "==> Stopping application workers for atomic recovery"
  docker compose stop sidecar >/dev/null 2>&1 || true
  docker compose stop odoo >/dev/null 2>&1 || true
  RESTART_SERVICES="true"
else
  echo "==> DRY RUN only. No database changes will be committed."
  echo "==> Rerun with CONFIRM_RECOVERY=YES after reviewing the match."
fi

docker compose run --rm -T --no-deps \
  -e RECOVERY_SOURCE_CAMPAIGN_ID="${SOURCE_CAMPAIGN_ID}" \
  -e RECOVERY_WINDOW_MINUTES="${WINDOW_MINUTES}" \
  -e EXPECTED_MESSAGES="${EXPECTED_MESSAGES}" \
  -e RECOVERY_PENDING_ACTION="${PENDING_ACTION}" \
  -e APPLY_RECOVERY="${APPLY_RECOVERY}" \
  odoo \
  python3 /opt/odoo/odoo-bin shell \
    -c "${CONFIG}" \
    -d "${LIVE_DB_NAME}" <<'PY'
import json
import os

apply_recovery = os.environ['APPLY_RECOVERY'].lower() == 'true'
result = env['whatsapp.campaign'].sudo().recover_deleted_campaign_messages(
    int(os.environ['RECOVERY_SOURCE_CAMPAIGN_ID']),
    apply=apply_recovery,
    window_minutes=int(os.environ['RECOVERY_WINDOW_MINUTES']),
    expected_message_count=int(os.environ['EXPECTED_MESSAGES']),
    pending_action=os.environ['RECOVERY_PENDING_ACTION'],
)
if apply_recovery:
    env.cr.commit()
else:
    env.cr.rollback()
print(json.dumps(result, indent=2, sort_keys=True))
PY

if [ "${APPLY_RECOVERY}" = "true" ]; then
  restart_services
  RESTART_SERVICES="false"
  if [ "${PENDING_ACTION}" = "resume" ]; then
    echo "==> Recovery complete. Existing pending rows were reattached for normal processing."
  else
    echo "==> Recovery complete. The recovered campaign is Cancelled and cannot send pending rows."
  fi
fi
