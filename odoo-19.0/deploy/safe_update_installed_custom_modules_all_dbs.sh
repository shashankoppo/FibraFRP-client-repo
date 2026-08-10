#!/usr/bin/env bash
set -euo pipefail

DB_USER="${POSTGRES_USER:-odoo}"
CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
OUTPUT_DIR="${OUTPUT_DIR:-secure_backups}"
DB_NAME_EXCLUDES="${DB_NAME_EXCLUDES:-postgres}"
EXTRA_UPGRADE_MODULES="${EXTRA_UPGRADE_MODULES:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

if [ "${CONFIRM_ALL_DBS:-NO}" != "YES" ]; then
  echo "ERROR: set CONFIRM_ALL_DBS=YES to upgrade every application database." >&2
  echo "This guard prevents accidental tenant-wide changes." >&2
  exit 2
fi

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  echo "ERROR: BACKUP_PASSPHRASE is required. Refusing all-DB upgrade without encrypted backups." >&2
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

sql_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "${value}"
}

join_sql_list() {
  local out=""
  local item
  for item in "$@"; do
    if [ -z "${out}" ]; then
      out="$(sql_quote "${item}")"
    else
      out="${out},$(sql_quote "${item}")"
    fi
  done
  printf '%s' "${out}"
}

join_csv() {
  local out=""
  local item
  for item in "$@"; do
    [ -n "${item}" ] || continue
    if [ -z "${out}" ]; then
      out="${item}"
    else
      out="${out},${item}"
    fi
  done
  printf '%s' "${out}"
}

CUSTOM_MODULES=()
for manifest in custom_addons/*/__manifest__.py; do
  [ -f "${manifest}" ] || continue
  CUSTOM_MODULES+=("$(basename "$(dirname "${manifest}")")")
done

if [ -n "${EXTRA_UPGRADE_MODULES}" ]; then
  IFS=',' read -r -a EXTRA_MODULES <<< "${EXTRA_UPGRADE_MODULES}"
  for module in "${EXTRA_MODULES[@]}"; do
    module="$(printf '%s' "${module}" | xargs)"
    [ -n "${module}" ] && CUSTOM_MODULES+=("${module}")
  done
fi

if [ "${#CUSTOM_MODULES[@]}" -eq 0 ]; then
  echo "ERROR: no custom modules found under custom_addons." >&2
  exit 1
fi

CUSTOM_MODULE_SQL="$(join_sql_list "${CUSTOM_MODULES[@]}")"
EXCLUDE_SQL="'$(echo "${DB_NAME_EXCLUDES}" | sed "s/,/','/g")'"

if [[ "${OUTPUT_DIR}" != /* ]]; then
  OUTPUT_DIR="${PROJECT_DIR}/${OUTPUT_DIR}"
fi
mkdir -p "${OUTPUT_DIR}"

echo "==> Safe installed-custom-module update for all client databases"
echo "==> Module candidates come from custom_addons plus EXTRA_UPGRADE_MODULES"
echo "==> Missing/uninstalled modules are not installed; each DB keeps its own module set"

echo "==> Ensuring PostgreSQL is running"
docker compose up -d db

mapfile -t DATABASES < <(
  docker compose exec -T db psql -U "${DB_USER}" -d postgres -Atc \
    "SELECT datname
       FROM pg_database
      WHERE datistemplate = false
        AND datallowconn = true
        AND datname NOT IN (${EXCLUDE_SQL})
      ORDER BY datname;"
)

if [ "${#DATABASES[@]}" -eq 0 ]; then
  echo "No application databases found. Nothing to update."
  exit 0
fi

echo "==> Target databases: ${DATABASES[*]}"

for DB in "${DATABASES[@]}"; do
  echo
  echo "---- Creating encrypted backup for ${DB}"
  OUTPUT_DIR="${OUTPUT_DIR}" BACKUP_PASSPHRASE="${BACKUP_PASSPHRASE}" \
    bash deploy/export_live_encrypted_backup.sh "${DB}"
done

echo
echo "==> Building Odoo image once"
docker compose build odoo

echo "==> Stopping Odoo and WhatsApp sidecar for clean upgrades"
docker compose stop sidecar >/dev/null 2>&1 || true
docker compose stop odoo >/dev/null 2>&1 || true

for DB in "${DATABASES[@]}"; do
  echo
  echo "---- Detecting installed custom modules on ${DB}"
  mapfile -t INSTALLED_MODULES < <(
    docker compose exec -T db psql -U "${DB_USER}" -d "${DB}" -Atc \
      "SELECT name
         FROM ir_module_module
        WHERE state = 'installed'
          AND name IN (${CUSTOM_MODULE_SQL})
        ORDER BY name;"
  )

  if [ "${#INSTALLED_MODULES[@]}" -eq 0 ]; then
    echo "---- No installed custom modules found on ${DB}; skipping module upgrade."
    continue
  fi

  MODULE_CSV="$(join_csv "${INSTALLED_MODULES[@]}")"
  echo "---- Upgrading on ${DB}: ${MODULE_CSV}"
  docker compose run --rm -T --no-deps odoo \
    python3 /opt/odoo/odoo-bin \
      -c "${CONFIG}" \
      -d "${DB}" \
      -u "${MODULE_CSV}" \
      --stop-after-init
done

echo
echo "==> Starting Odoo and WhatsApp sidecar"
docker compose up -d odoo sidecar

echo "==> Container status"
docker compose ps

echo
echo "==> Safe installed-custom-module all-DB update complete."
echo "Encrypted backups are in: ${OUTPUT_DIR}"
echo "Face sidecar remains disabled unless explicitly started with:"
echo "    docker compose --profile face up -d face_sidecar"
echo "Check logs with:"
echo "    docker logs --tail 250 odoo_app"
