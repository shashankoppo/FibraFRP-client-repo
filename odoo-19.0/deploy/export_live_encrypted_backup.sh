#!/usr/bin/env bash
set -euo pipefail

LIVE_DB_NAME="${1:-${LIVE_DB_NAME:-FiberaFRP_DB}}"
DB_USER="${POSTGRES_USER:-odoo}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  echo "ERROR: Set BACKUP_PASSPHRASE before exporting live data." >&2
  echo "Example: BACKUP_PASSPHRASE='use-a-long-secret' bash deploy/export_live_encrypted_backup.sh ${LIVE_DB_NAME}" >&2
  exit 1
fi

sql_quote() {
  local value="${1//\'/\'\'}"
  printf "'%s'" "${value}"
}

SAFE_DB_NAME="$(printf '%s' "${LIVE_DB_NAME}" | tr -c 'A-Za-z0-9_.-' '_')"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_DIR}/secure_backups}"
ARCHIVE_PATH="${OUTPUT_DIR}/${SAFE_DB_NAME}_${TIMESTAMP}_portable.tar.gz.enc"
WORK_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "${WORK_DIR}"
}
trap cleanup EXIT

mkdir -p "${OUTPUT_DIR}"
chmod 700 "${OUTPUT_DIR}" >/dev/null 2>&1 || true

echo "==> Exporting encrypted production bundle for ${LIVE_DB_NAME}"
echo "==> Output: ${ARCHIVE_PATH}"
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

echo "==> Dumping PostgreSQL database"
docker compose exec -T db pg_dump -U "${DB_USER}" -d "${LIVE_DB_NAME}" --format=custom \
  > "${WORK_DIR}/${SAFE_DB_NAME}.pg_dump"

echo "==> Capturing filestore if present"
if docker compose run --rm -T --no-deps --entrypoint sh -e LIVE_DB_NAME="${LIVE_DB_NAME}" odoo -c \
  'test -d "/root/.local/share/Odoo/filestore/${LIVE_DB_NAME}"'; then
  docker compose run --rm -T --no-deps --entrypoint sh -e LIVE_DB_NAME="${LIVE_DB_NAME}" odoo -c \
    'tar -C /root/.local/share/Odoo/filestore -czf - "${LIVE_DB_NAME}"' \
    > "${WORK_DIR}/${SAFE_DB_NAME}_filestore.tgz"
else
  echo "---- No filestore directory found for ${LIVE_DB_NAME}; writing empty marker."
  touch "${WORK_DIR}/NO_FILESTORE_FOUND"
fi

echo "==> Capturing deploy config files into the encrypted bundle"
mkdir -p "${WORK_DIR}/config"
for file in docker-compose.yml odoo.docker.conf .env; do
  if [ -f "${PROJECT_DIR}/${file}" ]; then
    cp "${PROJECT_DIR}/${file}" "${WORK_DIR}/config/${file}"
  fi
done

cat > "${WORK_DIR}/MANIFEST.txt" <<EOF
FiberaFRP portable encrypted backup
Database: ${LIVE_DB_NAME}
Created: ${TIMESTAMP}
Git commit: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)

Included:
- PostgreSQL custom-format dump
- Odoo filestore archive when present
- Local Docker/Odoo config files when present

Security:
- This archive can contain customer records, invoices, WhatsApp data, Meta tokens,
  app secrets, and other production credentials.
- Do not commit it to GitHub.
- Store it only in secure private storage.
EOF

echo "==> Encrypting archive"
tar -C "${WORK_DIR}" -czf - . | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
  -pass env:BACKUP_PASSPHRASE \
  -out "${ARCHIVE_PATH}"
chmod 600 "${ARCHIVE_PATH}" >/dev/null 2>&1 || true

echo
echo "==> Encrypted backup ready:"
echo "${ARCHIVE_PATH}"
echo
echo "Do not push this archive to GitHub. Move it through secure private storage only."
