#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${1:-}"
COUNTRY_CODE="${2:-IN}"
ADMIN_LOGIN="${3:-admin}"
ADMIN_LANGUAGE="${ADMIN_LANGUAGE:-en_US}"
CONFIG="${ODOO_CONFIG:-/etc/odoo/odoo.conf}"
INSTALL_MODULES="${INSTALL_MODULES:?An explicit initial module list is required}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

if [ "${CONFIRM_CREATE_DB:-NO}" != "YES" ]; then
  echo "ERROR: set CONFIRM_CREATE_DB=YES to create a new client database." >&2
  exit 2
fi
if [[ ! "${DB_NAME}" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "ERROR: database name must contain only letters, numbers, and underscores." >&2
  exit 2
fi
COUNTRY_CODE="$(printf '%s' "${COUNTRY_CODE}" | tr '[:lower:]' '[:upper:]')"
if [[ ! "${COUNTRY_CODE}" =~ ^[A-Z]{2}$ ]]; then
  echo "ERROR: country must be a two-letter ISO code such as IN." >&2
  exit 2
fi
if [ -z "${NEW_DB_ADMIN_PASSWORD:-}" ]; then
  echo "ERROR: NEW_DB_ADMIN_PASSWORD is required." >&2
  exit 1
fi

echo "==> Ensuring PostgreSQL is running"
docker compose up -d db

EXISTS="$(
  docker compose exec -T db psql -X -v ON_ERROR_STOP=1     -U "${POSTGRES_USER:-odoo}" -d postgres -Atc     "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = '${DB_NAME//\'/\'\'}');"
)"
if [ "${EXISTS}" = "t" ]; then
  echo "ERROR: database ${DB_NAME} already exists; refusing to overwrite it." >&2
  exit 1
fi

echo "==> Building latest Odoo CE image"
docker compose build odoo


echo "==> Creating ${DB_NAME} for country ${COUNTRY_CODE}"
docker compose run --rm -T --no-deps \
  --entrypoint /bin/bash \
  -e TARGET_DB="${DB_NAME}" \
  -e TARGET_COUNTRY="${COUNTRY_CODE}" \
  -e TARGET_ADMIN_LOGIN="${ADMIN_LOGIN}" \
  -e TARGET_ADMIN_LANGUAGE="${ADMIN_LANGUAGE}" \
  -e TARGET_ADMIN_PASSWORD="${NEW_DB_ADMIN_PASSWORD}" \
  odoo -lc '
    exec python3 /opt/odoo/odoo-bin db \
      -c "${ODOO_RC}" \
      --db_host="${DB_HOST}" \
      --db_port="${DB_PORT}" \
      --db_user="${DB_USER}" \
      --db_password="${DB_PASSWORD}" \
      init "${TARGET_DB}" \
      --country "${TARGET_COUNTRY}" \
      --language "${TARGET_ADMIN_LANGUAGE}" \
      --username "${TARGET_ADMIN_LOGIN}" \
      --password "${TARGET_ADMIN_PASSWORD}"
  '

echo "==> Installing explicitly selected modules and their dependencies"
docker compose run --rm -T --no-deps   -e ELSX_NATIVE_ADMIN_CLEANUP=NO   odoo   python3 /opt/odoo/odoo-bin     -c "${CONFIG}"     -d "${DB_NAME}"     -i "${INSTALL_MODULES}"     --without-demo=True     --stop-after-init     --no-http

PENDING="$(
  docker compose exec -T db psql -X -v ON_ERROR_STOP=1     -U "${POSTGRES_USER:-odoo}" -d "${DB_NAME}" -Atc     "SELECT COALESCE(string_agg(name || ':' || state, ',' ORDER BY name), '')
       FROM ir_module_module
      WHERE state IN ('to install', 'to upgrade', 'to remove');"
)"
if [ -n "${PENDING}" ]; then
  echo "ERROR: pending module states remain: ${PENDING}" >&2
  exit 1
fi

echo "==> Verifying every explicitly requested module is installed"
docker compose run --rm -T --no-deps \
  --entrypoint python3 \
  -e DEPLOY_DB="${DB_NAME}" \
  -e EXPECTED_INSTALL_MODULES="${INSTALL_MODULES}" \
  odoo /opt/odoo/deploy/guarded_upgrade.py verify-new

if ! docker compose up -d --no-deps --wait --wait-timeout 240 odoo; then
  docker compose stop -t 30 odoo
  echo "ERROR: startup health checks failed; the new database is retained for investigation." >&2
  exit 1
fi
docker compose ps

echo
echo "==> New client database is ready: ${DB_NAME}"
echo "Country profile: ${COUNTRY_CODE}"
echo "Administrator login: ${ADMIN_LOGIN}"
echo "Selected modules and required dependencies are installed."
