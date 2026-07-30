#!/usr/bin/env bash
set -euo pipefail

case "${ELSX_NATIVE_ADMIN_CLEANUP:-YES}" in
  1|true|TRUE|yes|YES|on|ON) ;;
  *)
    echo "[native-admin-cleanup] Disabled by ELSX_NATIVE_ADMIN_CLEANUP."
    exit 0
    ;;
esac

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-odoo}"
DB_PASSWORD="${DB_PASSWORD:-}"
ODOO_CONFIG="${ODOO_RC:-/etc/odoo/odoo.conf}"
ODOO_BIN="${ODOO_BIN:-/opt/odoo/odoo-bin}"
TARGET_DBS="${ELSX_NATIVE_ADMIN_CLEANUP_DBS:-}"
EXPECTED_MODULE_VERSIONS="'2.8.6','19.0.2.8.6'"
EXPECTED_REBRAND_VERSIONS="'1.2.1','19.0.1.2.1'"
EXPECTED_DIALOG_VERSIONS="'19.0.1.0.4'"
EXPECTED_APPSBAR_VERSIONS="'19.0.1.1.3'"
EXPECTED_THEME_VERSIONS="'19.0.1.4.2'"
ASSET_PURGE_MARKER="rebrand-qweb-safe-1.2.1"

log() {
  printf '[native-admin-cleanup] %s\n' "$*" >&2
}

if [ -z "${DB_PASSWORD}" ]; then
  log 'DB_PASSWORD is empty; skipping cleanup.'
  exit 0
fi

psql_db() {
  local database="$1"
  shift
  PGPASSWORD="${DB_PASSWORD}" psql \
    -X -v ON_ERROR_STOP=1 \
    -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${database}" \
    "$@"
}


clear_broken_menu_actions() {
  local database="$1"
  if ! removed_menus="$(
    psql_db "${database}" -Atc "
      WITH broken AS (
        SELECT m.id
          FROM ir_ui_menu m
         WHERE m.action IS NOT NULL
           AND m.action::text <> ''
           AND split_part(m.action::text, ',', 2) ~ '^[0-9]+$'
           AND (
             (split_part(m.action::text, ',', 1) = 'ir.actions.server'
              AND NOT EXISTS (SELECT 1 FROM ir_act_server a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
             OR (split_part(m.action::text, ',', 1) = 'ir.actions.act_window'
              AND NOT EXISTS (SELECT 1 FROM ir_act_window a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
             OR (split_part(m.action::text, ',', 1) = 'ir.actions.act_url'
              AND NOT EXISTS (SELECT 1 FROM ir_act_url a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
             OR (split_part(m.action::text, ',', 1) = 'ir.actions.client'
              AND NOT EXISTS (SELECT 1 FROM ir_act_client a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
             OR (split_part(m.action::text, ',', 1) = 'ir.actions.report'
              AND NOT EXISTS (SELECT 1 FROM ir_act_report_xml a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
             OR split_part(m.action::text, ',', 1) NOT IN (
                'ir.actions.server',
                'ir.actions.act_window',
                'ir.actions.act_url',
                'ir.actions.client',
                'ir.actions.report'
             )
           )
      ), cleared AS (
        UPDATE ir_ui_menu
           SET action = NULL,
               write_date = NOW()
         WHERE id IN (SELECT id FROM broken)
         RETURNING id
      )
      SELECT COUNT(*) FROM cleared;"
  )"; then
    log "Broken menu-action cleanup failed in ${database}; Odoo will continue startup."
    return 0
  fi
  if [ "${removed_menus}" != '0' ]; then
    log "Cleared ${removed_menus} broken menu action pointer(s) in ${database}."
  fi
}

purge_generated_assets() {
  local database="$1"
  if ! has_attachments="$(
    psql_db "${database}" -Atc "SELECT to_regclass('public.ir_attachment') IS NOT NULL;"
  )"; then
    log "Skipping generated asset purge in ${database}; could not inspect attachment table."
    return 0
  fi
  if [ "${has_attachments}" != 't' ]; then
    return 0
  fi

  if ! removed_assets="$(
    psql_db "${database}" -Atc "
      WITH removed AS (
        DELETE FROM ir_attachment
         WHERE COALESCE(url, '') LIKE '/web/assets/%'
         RETURNING id
      )
      SELECT COUNT(*) FROM removed;"
  )"; then
    log "Generated asset purge failed in ${database}; Odoo will continue startup."
    return 0
  fi
  log "Purged ${removed_assets} generated web asset attachment(s) in ${database}."
  psql_db "${database}" -c "
    INSERT INTO ir_config_parameter (key, value, create_uid, create_date, write_uid, write_date)
    VALUES ('elsx_rebrand.generated_assets_purge', '${ASSET_PURGE_MARKER}', 1, NOW(), 1, NOW())
    ON CONFLICT (key) DO UPDATE
      SET value = EXCLUDED.value,
          write_uid = EXCLUDED.write_uid,
          write_date = EXCLUDED.write_date;" >/dev/null || true
}
if [ -n "${TARGET_DBS}" ]; then
  database_list="$(printf '%s' "${TARGET_DBS}" | tr ',' '\n')"
else
  if ! database_list="$(
    psql_db postgres -Atc \
      "SELECT datname FROM pg_database
        WHERE datistemplate = false
          AND datallowconn = true
          AND datname <> 'postgres'
        ORDER BY datname;"
  )"; then
    log 'Could not connect to PostgreSQL for startup cleanup; Odoo will start without applying cleanup/rebrand.'
    exit 0
  fi
fi

while IFS= read -r database; do
  [ -n "${database}" ] || continue

  if ! has_modules="$(
    psql_db "${database}" -Atc "SELECT to_regclass('public.ir_module_module') IS NOT NULL;"
  )"; then
    log "Skipping ${database}; could not inspect module table."
    continue
  fi
  if [ "${has_modules}" != 't' ]; then
    log "Skipping non-Odoo database ${database}."
    continue
  fi

  clear_broken_menu_actions "${database}"

  if ! needs_cleanup="$(
    psql_db "${database}" -Atc "
      SELECT CASE WHEN
        NOT EXISTS (
          SELECT 1
            FROM ir_module_module
           WHERE name = 'elsx_client_restrictions'
             AND state = 'installed'
        )
        OR EXISTS (
          SELECT 1
            FROM ir_module_module
           WHERE name = 'elsx_client_restrictions'
             AND state = 'installed'
             AND COALESCE(latest_version, '') NOT IN (${EXPECTED_MODULE_VERSIONS})
        )
        OR EXISTS (
          SELECT 1
            FROM ir_ui_menu m
           WHERE m.action IS NOT NULL
             AND m.action::text <> ''
             AND split_part(m.action::text, ',', 2) ~ '^[0-9]+$'
             AND (
               (split_part(m.action::text, ',', 1) = 'ir.actions.server'
                AND NOT EXISTS (SELECT 1 FROM ir_act_server a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
               OR (split_part(m.action::text, ',', 1) = 'ir.actions.act_window'
                AND NOT EXISTS (SELECT 1 FROM ir_act_window a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
               OR (split_part(m.action::text, ',', 1) = 'ir.actions.act_url'
                AND NOT EXISTS (SELECT 1 FROM ir_act_url a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
               OR (split_part(m.action::text, ',', 1) = 'ir.actions.client'
                AND NOT EXISTS (SELECT 1 FROM ir_act_client a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
               OR (split_part(m.action::text, ',', 1) = 'ir.actions.report'
                AND NOT EXISTS (SELECT 1 FROM ir_act_report_xml a WHERE a.id = split_part(m.action::text, ',', 2)::integer))
               OR split_part(m.action::text, ',', 1) NOT IN ('ir.actions.server','ir.actions.act_window','ir.actions.act_url','ir.actions.client','ir.actions.report')
             )
        )
        OR EXISTS (
          SELECT 1
            FROM ir_model_data
           WHERE module = 'elsx_client_restrictions'
             AND name IN (
               'menu_elsx_module_safety',
               'action_elsx_module_safety_wizard',
               'view_elsx_module_safety_wizard_form',
               'group_secret_apps_access',
               'action_apps_password_gate',
               'view_apps_password_unlock_form'
             )
        )
        OR EXISTS (
          SELECT 1
            FROM ir_ui_menu
           WHERE COALESCE(name::text, '') ILIKE '%Safe Module Change%'
        )
        OR EXISTS (
          SELECT 1
            FROM ir_config_parameter
           WHERE key = 'elsx_client_restrictions.apps_secret_token'
        )
        OR NOT EXISTS (
          SELECT 1
            FROM ir_config_parameter
           WHERE key = 'elsx_client_restrictions.apps_password_hash'
        )
        OR NOT EXISTS (
          SELECT 1
            FROM ir_module_module
           WHERE name = 'elsx_rebrand'
             AND state = 'installed'
        )
        OR EXISTS (
          SELECT 1
            FROM ir_module_module
           WHERE name = 'elsx_rebrand'
             AND state = 'installed'
             AND COALESCE(latest_version, '') NOT IN (${EXPECTED_REBRAND_VERSIONS})
        )
        OR NOT EXISTS (
          SELECT 1
            FROM ir_config_parameter
           WHERE key = 'elsx_rebrand.generated_assets_purge'
             AND value = '${ASSET_PURGE_MARKER}'
        )
        OR EXISTS (
          SELECT 1
            FROM ir_module_module
           WHERE name = 'muk_web_dialog'
             AND state = 'installed'
             AND COALESCE(latest_version, '') NOT IN (${EXPECTED_DIALOG_VERSIONS})
        )
        OR EXISTS (
          SELECT 1
            FROM ir_module_module
           WHERE name = 'muk_web_appsbar'
             AND state = 'installed'
             AND COALESCE(latest_version, '') NOT IN (${EXPECTED_APPSBAR_VERSIONS})
        )
        OR EXISTS (
          SELECT 1
            FROM ir_module_module
           WHERE name = 'muk_web_theme'
             AND state = 'installed'
             AND COALESCE(latest_version, '') NOT IN (${EXPECTED_THEME_VERSIONS})
        )
      THEN 't' ELSE 'f' END;"
  )"; then
    log "Skipping ${database}; could not inspect cleanup/rebrand state."
    continue
  fi

  if [ "${needs_cleanup}" != 't' ]; then
    log "${database} already has native administration metadata, Apps lock, and ELSxGlobal rebrand."
    continue
  fi

  upgrade_modules="elsx_client_restrictions,elsx_rebrand"
  if optional_ui_modules="$(
    psql_db "${database}" -Atc "
      SELECT COALESCE(string_agg(name, ',' ORDER BY name), '')
        FROM ir_module_module
       WHERE name IN ('muk_web_dialog','muk_web_appsbar','muk_web_theme')
         AND state = 'installed';"
  )" && [ -n "${optional_ui_modules}" ]; then
    upgrade_modules="${upgrade_modules},${optional_ui_modules}"
  fi

  log "Applying native administration cleanup, Apps lock, ELSxGlobal rebrand, and installed UI compatibility fixes in ${database}."
  if ! python3 "${ODOO_BIN}" \
    -c "${ODOO_CONFIG}" \
    --db_host="${DB_HOST}" \
    --db_port="${DB_PORT}" \
    --db_user="${DB_USER}" \
    --db_password="${DB_PASSWORD}" \
    -d "${database}" \
    -i elsx_client_restrictions,elsx_rebrand \
    -u "${upgrade_modules}" \
    --without-demo=True \
    --stop-after-init \
    --no-http \
    --log-level=error; then
    log "Cleanup/rebrand failed in ${database}; Odoo will continue startup so the database can be inspected."
  fi
  purge_generated_assets "${database}"

done <<< "${database_list}"