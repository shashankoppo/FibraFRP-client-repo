#!/usr/bin/env bash
set -euo pipefail

LIVE_DB_NAME="${1:-${LIVE_DB_NAME:-FiberaFRP_DB}}"
MODULES="${MODULES:-elsx_client_restrictions,elsx_whatsapp_marketing,elsx_attendance_tracking,elsx_tally_integration}"
CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
DB_USER="${POSTGRES_USER:-odoo}"

sql_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "${value}"
}

LIVE_DB_SQL="$(sql_quote "${LIVE_DB_NAME}")"

echo "==> Production database: ${LIVE_DB_NAME}"
echo "==> Modules to upgrade: ${MODULES}"

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

echo "==> Upgrading live database modules"
docker compose run --rm -T --no-deps odoo \
  python3 /opt/odoo/odoo-bin \
    -c "${CONFIG}" \
    -d "${LIVE_DB_NAME}" \
    -u "${MODULES}" \
    --stop-after-init

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
    docker compose exec -T db psql -U "${DB_USER}" -d "${DB}" -c \
      "UPDATE whatsapp_account
          SET is_primary_webhook_db = true
        WHERE active = true;" >/dev/null
    echo "---- ${DB}: active WhatsApp account(s) marked primary"
  else
    docker compose exec -T db psql -U "${DB_USER}" -d "${DB}" -c \
      "UPDATE whatsapp_account
          SET is_primary_webhook_db = false;" >/dev/null
    echo "---- ${DB}: WhatsApp webhook primary flag disabled"
  fi
done

echo "==> Live WhatsApp account status"
docker compose exec -T db psql -U "${DB_USER}" -d "${LIVE_DB_NAME}" -c \
  "SELECT id, name, phone_number, webhook_status, is_primary_webhook_db
     FROM whatsapp_account
    ORDER BY id;"

echo "==> Starting Odoo and sidecar"
docker compose up -d odoo sidecar

echo "==> Done."
echo "Use this Meta webhook callback URL:"
echo "    https://YOUR_DOMAIN/whatsapp/webhook/1?db=${LIVE_DB_NAME}"
echo "Then verify logs with:"
echo "    docker logs --tail 200 odoo_app"
echo "    docker logs --tail 100 whatsapp_sidecar"
