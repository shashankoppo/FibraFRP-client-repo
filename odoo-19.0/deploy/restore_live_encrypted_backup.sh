#!/usr/bin/env bash
set -euo pipefail

ARCHIVE_PATH="${1:-}"
TARGET_DB_NAME="${2:-${LIVE_DB_NAME:-FiberaFRP_DB}}"
DB_USER="${POSTGRES_USER:-odoo}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

if [ -z "${ARCHIVE_PATH}" ]; then
  echo "ERROR: Missing encrypted archive path." >&2
  echo "Usage: CONFIRM_RESTORE=YES BACKUP_PASSPHRASE='secret' bash deploy/restore_live_encrypted_backup.sh /path/to/archive.enc ${TARGET_DB_NAME}" >&2
  exit 1
fi
if [ ! -f "${ARCHIVE_PATH}" ]; then
  echo "ERROR: Archive not found: ${ARCHIVE_PATH}" >&2
  exit 1
fi
ARCHIVE_DIR="$(cd "$(dirname "${ARCHIVE_PATH}")" && pwd -P)"
ARCHIVE_BASENAME="$(basename "${ARCHIVE_PATH}")"
ARCHIVE_PATH="${ARCHIVE_DIR}/${ARCHIVE_BASENAME}"
if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  echo "ERROR: Set BACKUP_PASSPHRASE before restoring." >&2
  exit 1
fi
if [ "${CONFIRM_RESTORE:-}" != "YES" ]; then
  echo "ERROR: Restore is intentionally guarded because it overwrites ${TARGET_DB_NAME}." >&2
  echo "Rerun with CONFIRM_RESTORE=YES after confirming you have the right archive." >&2
  exit 1
fi

sql_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "${value}"
}

SAFE_DB_NAME="$(printf '%s' "${TARGET_DB_NAME}" | tr -c 'A-Za-z0-9_.-' '_')"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
WORK_DIR="$(mktemp -d)"
PRE_RESTORE_DIR="${PRE_RESTORE_DIR:-${PROJECT_DIR}/secure_backups/pre_restore_${SAFE_DB_NAME}_${TIMESTAMP}}"

cleanup() {
  rm -rf "${WORK_DIR}"
}
trap cleanup EXIT

echo "==> Restoring encrypted backup into database ${TARGET_DB_NAME}"
echo "==> This will replace the target database contents."
echo "==> Ensuring PostgreSQL is running"
docker compose up -d db

mkdir -p "${PRE_RESTORE_DIR}"
chmod 700 "${PRE_RESTORE_DIR}" >/dev/null 2>&1 || true

DB_EXISTS="$(
  docker compose exec -T db psql -U "${DB_USER}" -d postgres -Atc \
    "SELECT 1 FROM pg_database WHERE datname = $(sql_quote "${TARGET_DB_NAME}");"
)"
if [ "${DB_EXISTS}" = "1" ]; then
  echo "==> Creating pre-restore safety dump for existing ${TARGET_DB_NAME}"
  docker compose exec -T db pg_dump -U "${DB_USER}" -d "${TARGET_DB_NAME}" --format=custom \
    > "${PRE_RESTORE_DIR}/${SAFE_DB_NAME}_before_restore.pg_dump"
fi

echo "==> Decrypting archive"
if command -v openssl >/dev/null 2>&1; then
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -pass env:BACKUP_PASSPHRASE \
    -in "${ARCHIVE_PATH}" | tar -C "${WORK_DIR}" -xzf -
else
  echo "---- Host openssl not found; using openssl from the Odoo container."
  if ! docker compose run --rm -T --no-deps --entrypoint openssl odoo version >/dev/null 2>&1; then
    echo "ERROR: openssl is not available on the host or inside the Odoo image." >&2
    echo "Install openssl on the host, or add it to the Odoo image, then rerun." >&2
    exit 1
  fi
  docker compose run --rm -T --no-deps \
    -e BACKUP_PASSPHRASE \
    -v "${ARCHIVE_DIR}:/backup:ro" \
    --entrypoint openssl \
    odoo enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
      -pass env:BACKUP_PASSPHRASE \
      -in "/backup/${ARCHIVE_BASENAME}" | tar -C "${WORK_DIR}" -xzf -
fi

DUMP_FILE="$(find "${WORK_DIR}" -maxdepth 1 -type f -name '*.pg_dump' | head -n 1)"
FILESTORE_FILE="$(find "${WORK_DIR}" -maxdepth 1 -type f -name '*_filestore.tgz' | head -n 1 || true)"
if [ -z "${DUMP_FILE}" ]; then
  echo "ERROR: No PostgreSQL dump found inside archive." >&2
  exit 1
fi

echo "==> Stopping Odoo and sidecar during restore"
docker compose stop sidecar >/dev/null 2>&1 || true
docker compose stop odoo >/dev/null 2>&1 || true

echo "==> Recreating database ${TARGET_DB_NAME}"
docker compose exec -T db dropdb -U "${DB_USER}" --if-exists "${TARGET_DB_NAME}"
docker compose exec -T db createdb -U "${DB_USER}" "${TARGET_DB_NAME}"
docker compose exec -T db pg_restore -U "${DB_USER}" -d "${TARGET_DB_NAME}" --clean --if-exists \
  < "${DUMP_FILE}"

if [ -n "${FILESTORE_FILE}" ] && [ -s "${FILESTORE_FILE}" ]; then
  echo "==> Restoring filestore"
  docker compose run --rm -T --no-deps \
    --entrypoint sh \
    -v "${FILESTORE_FILE}:/tmp/filestore.tgz:ro" \
    -e TARGET_DB_NAME="${TARGET_DB_NAME}" \
    odoo -c '
      mkdir -p /root/.local/share/Odoo/filestore
      rm -rf "/root/.local/share/Odoo/filestore/${TARGET_DB_NAME}"
      tar -xzf /tmp/filestore.tgz -C /root/.local/share/Odoo/filestore
    '
else
  echo "---- No filestore archive found inside backup; skipping filestore restore."
fi

if [ "${RESTORE_CONFIG:-}" = "YES" ] && [ -d "${WORK_DIR}/config" ]; then
  echo "==> Restoring selected config files"
  mkdir -p "${PRE_RESTORE_DIR}/config_before_restore"
  for file in .env odoo.docker.conf; do
    if [ -f "${WORK_DIR}/config/${file}" ]; then
      if [ -f "${PROJECT_DIR}/${file}" ]; then
        cp "${PROJECT_DIR}/${file}" "${PRE_RESTORE_DIR}/config_before_restore/${file}"
      fi
      cp "${WORK_DIR}/config/${file}" "${PROJECT_DIR}/${file}"
      echo "---- Restored ${file}"
    fi
  done
elif [ -d "${WORK_DIR}/config" ]; then
  echo "---- Config files are inside the archive but were not restored."
  echo "---- Set RESTORE_CONFIG=YES if you intentionally want to restore .env/odoo.docker.conf."
fi

echo "==> Starting Odoo and sidecar"
docker compose up -d odoo sidecar

echo
echo "==> Restore finished."
echo "Pre-restore safety dump directory: ${PRE_RESTORE_DIR}"
echo "Open the restored database, then verify login, Invoicing, WhatsApp Marketing,"
echo "Team Inbox, webhook account settings, and one incoming WhatsApp test message."
