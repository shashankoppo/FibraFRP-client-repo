#!/usr/bin/env bash
set -euo pipefail

# Disable the SaaS runtime layer without uninstalling modules or deleting data.
# This script only updates technical Odoo metadata:
# - elsx_saas.enabled = 0
# - SaaS menu tree inactive
# - SaaS app-store override views inactive
# - SaaS cron jobs inactive
# - Apps URL token present for elsx_client_restrictions
# It does not drop databases, delete Docker volumes, uninstall modules, or touch
# business records such as contacts, invoices, WhatsApp chats, attendance, CRM,
# Tally, website, or filestore attachments.

DB_USER="${POSTGRES_USER:-odoo}"
DB_NAME_EXCLUDES="${DB_NAME_EXCLUDES:-postgres}"
TARGET_DBS="${TARGET_DBS:-}"
CONFIRM_DEACTIVATE_SAAS="${CONFIRM_DEACTIVATE_SAAS:-NO}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

if [ "${CONFIRM_DEACTIVATE_SAAS}" != "YES" ]; then
  echo "ERROR: set CONFIRM_DEACTIVATE_SAAS=YES to disable SaaS runtime metadata." >&2
  echo "Example: CONFIRM_DEACTIVATE_SAAS=YES TARGET_DBS=FiberaFRP_DB bash deploy/deactivate_saas_all_dbs.sh" >&2
  exit 2
fi

if [ -z "${TARGET_DBS}" ] && [ "${CONFIRM_ALL_DBS:-NO}" != "YES" ]; then
  echo "ERROR: set TARGET_DBS=db1,db2 or CONFIRM_ALL_DBS=YES." >&2
  echo "This guard prevents accidental tenant-wide metadata changes." >&2
  exit 2
fi

sql_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "${value}"
}

wait_for_db() {
  local attempt
  for attempt in $(seq 1 60); do
    if docker compose exec -T db pg_isready -U "${DB_USER}" -d postgres >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "ERROR: PostgreSQL did not become ready after 120 seconds." >&2
  docker compose ps db >&2 || true
  exit 1
}

echo "==> Ensuring PostgreSQL is running"
docker compose up -d db >/dev/null
wait_for_db

EXCLUDE_SQL="'$(echo "${DB_NAME_EXCLUDES}" | sed "s/,/','/g")'"
DB_LIST_SQL="SELECT datname
               FROM pg_database
              WHERE datistemplate = false
                AND datallowconn = true
                AND datname NOT IN (${EXCLUDE_SQL})
              ORDER BY datname;"
DB_LIST_OUTPUT="$(docker compose exec -T db psql -U "${DB_USER}" -d postgres -Atc "${DB_LIST_SQL}")"

if [ -n "${TARGET_DBS}" ]; then
  IFS=',' read -r -a REQUESTED_DATABASES <<< "${TARGET_DBS}"
  DATABASES=()
  for REQUESTED_DB in "${REQUESTED_DATABASES[@]}"; do
    REQUESTED_DB="$(echo "${REQUESTED_DB}" | xargs)"
    [ -z "${REQUESTED_DB}" ] && continue
    if ! printf '%s\n' "${DB_LIST_OUTPUT}" | grep -Fxq "${REQUESTED_DB}"; then
      echo "ERROR: requested database '${REQUESTED_DB}' was not found or is excluded." >&2
      echo "Available application databases:" >&2
      printf '%s\n' "${DB_LIST_OUTPUT}" >&2
      exit 1
    fi
    DATABASES+=("${REQUESTED_DB}")
  done
elif [ -n "${DB_LIST_OUTPUT}" ]; then
  mapfile -t DATABASES <<< "${DB_LIST_OUTPUT}"
else
  DATABASES=()
fi

if [ "${#DATABASES[@]}" -eq 0 ]; then
  echo "No application databases found. Nothing to deactivate."
  exit 0
fi

echo "==> Disabling SaaS runtime metadata in: ${DATABASES[*]}"

for DB in "${DATABASES[@]}"; do
  echo "---- ${DB}"
  docker compose exec -T db psql -U "${DB_USER}" -d "${DB}" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
DECLARE
  root_menu_id integer;
  apps_token text;
BEGIN
  IF to_regclass('public.ir_config_parameter') IS NOT NULL THEN
    INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
    VALUES ('elsx_saas.enabled', '0', 1, now(), 1, now())
    ON CONFLICT (key) DO UPDATE
       SET value = '0', write_uid = 1, write_date = now();

    SELECT value
      INTO apps_token
      FROM ir_config_parameter
     WHERE key = 'elsx_client_restrictions.apps_secret_token'
     LIMIT 1;

    IF COALESCE(apps_token, '') = '' THEN
      INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
      VALUES (
        'elsx_client_restrictions.apps_secret_token',
        substr(md5(random()::text || clock_timestamp()::text || txid_current()::text), 1, 32),
        1,
        now(),
        1,
        now()
      )
      ON CONFLICT (key) DO UPDATE
         SET value = EXCLUDED.value, write_uid = 1, write_date = now()
       WHERE COALESCE(ir_config_parameter.value, '') = '';
    END IF;
  END IF;

  IF to_regclass('public.ir_model_data') IS NOT NULL
     AND to_regclass('public.ir_cron') IS NOT NULL THEN
    UPDATE ir_cron AS c
       SET active = false
      FROM ir_model_data AS d
     WHERE d.model = 'ir.cron'
       AND d.module = 'elsx_saas'
       AND d.res_id = c.id;
  END IF;

  IF to_regclass('public.ir_model_data') IS NOT NULL
     AND to_regclass('public.ir_ui_view') IS NOT NULL THEN
    UPDATE ir_ui_view AS v
       SET active = false
      FROM ir_model_data AS d
     WHERE d.model = 'ir.ui.view'
       AND d.module = 'elsx_saas'
       AND d.name IN ('view_module_kanban_saas_override', 'view_module_form_saas_override')
       AND d.res_id = v.id;
  END IF;

  IF to_regclass('public.ir_model_data') IS NOT NULL
     AND to_regclass('public.ir_ui_menu') IS NOT NULL THEN
    SELECT res_id
      INTO root_menu_id
      FROM ir_model_data
     WHERE module = 'elsx_saas'
       AND name = 'menu_elsx_saas_root'
       AND model = 'ir.ui.menu'
     LIMIT 1;

    IF root_menu_id IS NOT NULL THEN
      WITH RECURSIVE menu_tree AS (
        SELECT id FROM ir_ui_menu WHERE id = root_menu_id
        UNION ALL
        SELECT child.id
          FROM ir_ui_menu child
          JOIN menu_tree parent ON child.parent_id = parent.id
      )
      UPDATE ir_ui_menu AS menu
         SET active = false
        FROM menu_tree
       WHERE menu.id = menu_tree.id;
    END IF;
  END IF;
END $$;
SQL

docker compose exec -T db psql -U "${DB_USER}" -d "${DB}" -Atc \
  "SELECT 'saas_enabled=' || COALESCE((SELECT value FROM ir_config_parameter WHERE key='elsx_saas.enabled' LIMIT 1), '<missing>') WHERE to_regclass('public.ir_config_parameter') IS NOT NULL;" || true

docker compose exec -T db psql -U "${DB_USER}" -d "${DB}" -Atc \
  "SELECT 'apps_url_token=' || CASE WHEN COALESCE((SELECT value FROM ir_config_parameter WHERE key='elsx_client_restrictions.apps_secret_token' LIMIT 1), '') = '' THEN 'missing' ELSE 'present' END WHERE to_regclass('public.ir_config_parameter') IS NOT NULL;" || true

done

echo "==> SaaS runtime deactivation complete. No modules were uninstalled and no client business data was modified."