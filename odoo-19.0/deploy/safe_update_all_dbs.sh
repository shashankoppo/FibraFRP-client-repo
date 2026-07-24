#!/usr/bin/env bash
set -euo pipefail

DB_USER="${POSTGRES_USER:-odoo}"
CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
OUTPUT_DIR="${OUTPUT_DIR:-secure_backups}"
DB_NAME_EXCLUDES="${DB_NAME_EXCLUDES:-postgres}"
TARGET_DBS="${TARGET_DBS:-}"
INSTALL_MODULES="${INSTALL_MODULES:-elsx_client_restrictions,elsx_attendance_tracking,elsx_face_attendance}"
UPGRADE_MODULES="${UPGRADE_MODULES:-elsx_client_restrictions,elsx_attendance_tracking,elsx_face_attendance}"
EXTRA_INSTALL_MODULES="${EXTRA_INSTALL_MODULES:-}"
EXTRA_UPGRADE_MODULES="${EXTRA_UPGRADE_MODULES:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

wait_for_db() {
  local attempt
  echo "==> Waiting for PostgreSQL to accept connections"
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

if [ -n "${TARGET_DBS}" ]; then
  if [ "${CONFIRM_TARGET_DBS:-NO}" != "YES" ]; then
    echo "ERROR: set CONFIRM_TARGET_DBS=YES when TARGET_DBS is used." >&2
    echo "Example: TARGET_DBS=FiberaFRP_DB CONFIRM_TARGET_DBS=YES BACKUP_PASSPHRASE=... bash deploy/safe_update_all_dbs.sh" >&2
    exit 2
  fi
elif [ "${CONFIRM_ALL_DBS:-NO}" != "YES" ]; then
  echo "ERROR: set CONFIRM_ALL_DBS=YES to upgrade every application database." >&2
  echo "For a single production DB, use TARGET_DBS=FiberaFRP_DB CONFIRM_TARGET_DBS=YES instead." >&2
  echo "This guard prevents accidental tenant-wide changes." >&2
  exit 2
fi

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  echo "ERROR: BACKUP_PASSPHRASE is required. Refusing all-DB upgrade without encrypted backups." >&2
  exit 1
fi

if [ "${ALLOW_DIRTY_CODE:-NO}" != "YES" ]; then
  if [ -n "$(git status --short --untracked-files=no)" ]; then
    echo "ERROR: tracked Git files are modified. Commit/stash or rerun with ALLOW_DIRTY_CODE=YES after review." >&2
    git status --short --untracked-files=no >&2
    exit 1
  fi
fi

ALL_INSTALL_MODULES="${INSTALL_MODULES}"
if [ -n "${EXTRA_INSTALL_MODULES}" ]; then
  ALL_INSTALL_MODULES="${ALL_INSTALL_MODULES},${EXTRA_INSTALL_MODULES}"
fi

ALL_UPGRADE_MODULES="${UPGRADE_MODULES}"
if [ -n "${EXTRA_UPGRADE_MODULES}" ]; then
  ALL_UPGRADE_MODULES="${ALL_UPGRADE_MODULES},${EXTRA_UPGRADE_MODULES}"
fi

echo "==> Safe all-database update"
echo "==> Install modules if missing: ${ALL_INSTALL_MODULES}"
echo "==> Upgrade modules: ${ALL_UPGRADE_MODULES}"

echo "==> Ensuring PostgreSQL is running"
docker compose up -d db
wait_for_db

EXCLUDE_SQL="'$(echo "${DB_NAME_EXCLUDES}" | sed "s/,/','/g")'"
DB_LIST_SQL="SELECT datname
               FROM pg_database
              WHERE datistemplate = false
                AND datallowconn = true
                AND datname NOT IN (${EXCLUDE_SQL})
              ORDER BY datname;"
if ! DB_LIST_OUTPUT="$(docker compose exec -T db psql -U "${DB_USER}" -d postgres -Atc "${DB_LIST_SQL}")"; then
  echo "ERROR: failed to list application databases. Refusing to continue." >&2
  exit 1
fi
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
  echo "No application databases found. Nothing to update."
  exit 0
fi

if [ -n "${TARGET_DBS}" ]; then
  echo "==> Target databases (explicit): ${DATABASES[*]}"
else
  echo "==> Target databases (all application DBs): ${DATABASES[*]}"
fi

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
  echo "---- Removing retired SaaS module on ${DB}"
  docker compose run --rm -T --no-deps odoo \
    bash /opt/odoo/deploy/remove_retired_saas_db.sh "${DB}"

  echo "---- Installing/upgrading modules on ${DB}"
  docker compose run --rm -T --no-deps odoo \
    python3 /opt/odoo/odoo-bin \
      -c "${CONFIG}" \
      -d "${DB}" \
      -i "${ALL_INSTALL_MODULES}" \
      -u "${ALL_UPGRADE_MODULES}" \
      --stop-after-init
done

echo
echo "==> Starting Odoo and WhatsApp sidecar"
docker compose up -d odoo sidecar

echo "==> Container status"
docker compose ps

echo
echo "==> Safe all-database update complete."
echo "Encrypted backups are in: ${OUTPUT_DIR}"
echo "Face sidecar remains disabled unless explicitly started with:"
echo "    docker compose --profile face up -d face_sidecar"
echo "Check logs with:"
echo "    docker logs --tail 250 odoo_app"
