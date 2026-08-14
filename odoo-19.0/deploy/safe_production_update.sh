#!/usr/bin/env bash
set -euo pipefail

LIVE_DB_NAME="${1:-${LIVE_DB_NAME:-}}"
DB_USER="${POSTGRES_USER:-odoo}"
CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
OUTPUT_DIR="${OUTPUT_DIR:-secure_backups}"
INSTALL_MODULES="${INSTALL_MODULES:-elsx_client_restrictions,elsx_rebrand,elsx_attendance_tracking,elsx_face_attendance}"
UPGRADE_MODULES="${UPGRADE_MODULES:-elsx_client_restrictions,elsx_rebrand,elsx_attendance_tracking,elsx_face_attendance}"
EXTRA_INSTALL_MODULES="${EXTRA_INSTALL_MODULES:-}"
EXTRA_UPGRADE_MODULES="${EXTRA_UPGRADE_MODULES:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

if [ -z "${LIVE_DB_NAME}" ]; then
  echo "ERROR: database name is required. This script will not guess a production database." >&2
  echo "Usage: BACKUP_PASSPHRASE=... bash deploy/safe_production_update.sh <database_name>" >&2
  echo "Example: read -s -p 'Backup passphrase: ' BACKUP_PASSPHRASE && echo && export BACKUP_PASSPHRASE && bash deploy/safe_production_update.sh FiberaFRP_DB" >&2
  exit 2
fi

sql_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "${value}"
}

SAFE_DB_NAME="$(printf '%s' "${LIVE_DB_NAME}" | tr -c 'A-Za-z0-9_.-' '_')"
if [[ "${OUTPUT_DIR}" != /* ]]; then
  OUTPUT_DIR="${PROJECT_DIR}/${OUTPUT_DIR}"
fi
mkdir -p "${OUTPUT_DIR}"

echo "==> Production-safe update for database: ${LIVE_DB_NAME}"
ALL_INSTALL_MODULES="${INSTALL_MODULES}"
if [ -n "${EXTRA_INSTALL_MODULES}" ]; then
  ALL_INSTALL_MODULES="${ALL_INSTALL_MODULES},${EXTRA_INSTALL_MODULES}"
fi

ALL_UPGRADE_MODULES="${UPGRADE_MODULES}"
if [ -n "${EXTRA_UPGRADE_MODULES}" ]; then
  ALL_UPGRADE_MODULES="${ALL_UPGRADE_MODULES},${EXTRA_UPGRADE_MODULES}"
fi

echo "==> Install modules if missing: ${ALL_INSTALL_MODULES}"
echo "==> Upgrade modules: ${ALL_UPGRADE_MODULES}"

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  echo "ERROR: BACKUP_PASSPHRASE is required. Refusing to upgrade without an encrypted backup." >&2
  echo "Example: read -s -p 'Backup passphrase: ' BACKUP_PASSPHRASE && echo && export BACKUP_PASSPHRASE && bash deploy/safe_production_update.sh ${LIVE_DB_NAME}" >&2
  exit 1
fi

if [ "${ALLOW_DIRTY_CODE:-NO}" != "YES" ]; then
  DIRTY_STATUS="$(git status --short --untracked-files=no)"
  BLOCKING_DIRTY_STATUS="$(printf '%s\n' "${DIRTY_STATUS}" | grep -vE '^ M custom_addons/elsx_whatsapp_marketing/sidecar/package-lock\.json$' || true)"
  if [ -n "${BLOCKING_DIRTY_STATUS}" ]; then
    echo "ERROR: tracked Git files are modified. Commit/stash or rerun with ALLOW_DIRTY_CODE=YES after review." >&2
    printf '%s\n' "${BLOCKING_DIRTY_STATUS}" >&2
    exit 1
  fi
  if [ -n "${DIRTY_STATUS}" ]; then
    echo "==> Ignoring generated sidecar package-lock.json dirty state"
  fi
fi

echo "==> Ensuring PostgreSQL is running"
docker compose up -d db

DB_EXISTS="$(
  docker compose exec -T db psql -U "${DB_USER}" -d postgres -Atc \
    "SELECT 1 FROM pg_database WHERE datname = $(sql_quote "${LIVE_DB_NAME}");"
)"
if [ "${DB_EXISTS}" != "1" ]; then
  echo "ERROR: Database ${LIVE_DB_NAME} does not exist." >&2
  exit 1
fi

echo "==> Creating encrypted backup before any module upgrade"
OUTPUT_DIR="${OUTPUT_DIR}" BACKUP_PASSPHRASE="${BACKUP_PASSPHRASE}" \
  bash deploy/export_live_encrypted_backup.sh "${LIVE_DB_NAME}"

LATEST_BACKUP="$(ls -t "${OUTPUT_DIR}/${SAFE_DB_NAME}"*_portable.tar.gz.enc 2>/dev/null | head -n 1 || true)"
if [ -z "${LATEST_BACKUP}" ] || [ ! -s "${LATEST_BACKUP}" ]; then
  echo "ERROR: encrypted backup was not created or is empty. Refusing to continue." >&2
  exit 1
fi
echo "==> Verified encrypted backup: ${LATEST_BACKUP}"

echo "==> Building Odoo image"
docker compose build odoo

echo "==> Stopping Odoo and WhatsApp sidecar for a clean module upgrade"
docker compose stop sidecar >/dev/null 2>&1 || true
docker compose stop odoo >/dev/null 2>&1 || true

echo "==> Installing/upgrading requested modules through the backup-protected path"
docker compose run --rm -T --no-deps odoo \
  python3 /opt/odoo/odoo-bin \
    -c "${CONFIG}" \
    -d "${LIVE_DB_NAME}" \
    -i "${ALL_INSTALL_MODULES}" \
    -u "${ALL_UPGRADE_MODULES}" \
    --stop-after-init

echo "==> Starting Odoo and WhatsApp sidecar"
docker compose up -d odoo sidecar

echo "==> Waiting for Odoo health check"
ODOO_HEALTHY="NO"
for _attempt in $(seq 1 30); do
  if docker compose exec -T odoo curl -fsS http://127.0.0.1:8069/web/health >/dev/null 2>&1; then
    ODOO_HEALTHY="YES"
    break
  fi
  sleep 4
done
if [ "${ODOO_HEALTHY}" != "YES" ]; then
  echo "ERROR: Odoo did not become healthy after the module upgrade." >&2
  docker logs --tail 250 odoo_app >&2 || true
  exit 1
fi

echo "==> Waiting for WhatsApp sidecar health check"
SIDECAR_HEALTHY="NO"
for _attempt in $(seq 1 30); do
  if docker compose exec -T sidecar wget -q -O /dev/null http://127.0.0.1:3000/health >/dev/null 2>&1; then
    SIDECAR_HEALTHY="YES"
    break
  fi
  sleep 2
done
if [ "${SIDECAR_HEALTHY}" != "YES" ]; then
  echo "ERROR: WhatsApp sidecar did not become healthy after the module upgrade." >&2
  docker logs --tail 250 whatsapp_sidecar >&2 || true
  exit 1
fi

case ",${ALL_INSTALL_MODULES},${ALL_UPGRADE_MODULES}," in
  *",elsx_whatsapp_marketing,"*)
    echo "==> Verifying WhatsApp contact import schema"
    NULLABLE_IMPORT_COLUMNS="$(
      docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -Atc \
        "SELECT COUNT(*)
           FROM information_schema.columns
          WHERE table_schema = 'public'
            AND table_name = 'whatsapp_contact'
            AND column_name IN ('name', 'phone_number')
            AND is_nullable = 'YES';"
    )"
    if [ "${NULLABLE_IMPORT_COLUMNS}" != "2" ]; then
      echo "ERROR: WhatsApp contact import schema verification failed." >&2
      exit 1
    fi

    echo "==> Verifying WhatsApp campaign delivery workers"
    ACTIVE_DELIVERY_WORKERS="$(
      docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -Atc \
        "WITH expected(model_name, action_code) AS (
             VALUES
               ('whatsapp.campaign', 'model._cron_process_global_queue()'),
               ('whatsapp.message', 'model._cron_process_broadcast_queue()'),
               ('whatsapp.scheduled.campaign', 'model._cron_process_scheduled_campaigns()'),
               ('whatsapp.message', 'model._cron_retry_failed()'),
               ('whatsapp.campaign.participant', 'model.process_drip_campaigns()'),
               ('whatsapp.bot.flow.log', 'model._cron_resume_delayed_flows()'),
               ('whatsapp.scheduled.message', 'model._cron_send_scheduled()'),
               ('whatsapp.campaign', 'model._cron_evaluate_ab_tests()'),
               ('whatsapp.account', 'model._cron_reset_daily_counters()'),
               ('whatsapp.webhook.log', 'model._cron_recover_received()')
           )
         SELECT COUNT(*)
           FROM expected
          WHERE EXISTS (
                SELECT 1
                  FROM ir_cron AS cron
                  JOIN ir_act_server AS action ON action.id = cron.ir_actions_server_id
                  JOIN ir_model AS model ON model.id = action.model_id
                 WHERE cron.active = TRUE
                   AND model.model = expected.model_name
                   AND action.code = expected.action_code
          );"
    )"
    if [ "${ACTIVE_DELIVERY_WORKERS}" != "10" ]; then
      echo "ERROR: Expected ten active WhatsApp ecosystem workers; found ${ACTIVE_DELIVERY_WORKERS}." >&2
      exit 1
    fi

    echo "==> WhatsApp contact reconciliation summary"
    docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
      "SELECT COUNT(*) AS imported_contacts,
              COUNT(partner_id) AS linked_partners,
              COUNT(*) FILTER (WHERE phone_number IS NOT NULL AND BTRIM(phone_number) != '') AS contacts_with_phone,
              COUNT(*) FILTER (WHERE phone_number IS NULL OR BTRIM(phone_number) = '') AS incomplete_contacts
         FROM whatsapp_contact;"
    ;;
esac

echo "==> Module state check"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT name, state, latest_version
     FROM ir_module_module
    WHERE name IN ('elsx_client_restrictions','elsx_rebrand','elsx_attendance_tracking','elsx_face_attendance','elsx_whatsapp_marketing','elsx_tally_integration','crm','account','hr_attendance')
    ORDER BY name;"

echo "==> Container status"
docker compose ps

echo
echo "==> Safe production update complete."
echo "Backup kept at: ${LATEST_BACKUP}"
echo "Face sidecar remains disabled unless explicitly started with:"
echo "    docker compose --profile face up -d face_sidecar"
echo "Check logs with:"
echo "    docker logs --tail 250 odoo_app"
