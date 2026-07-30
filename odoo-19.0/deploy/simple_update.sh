#!/usr/bin/env bash
set -euo pipefail

# Simple production update for ELSxGlobal Odoo deployments.
# Keeps named Docker volumes intact. Never runs docker compose down.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_DIR}"

INSTALL_MODULES="${INSTALL_MODULES:-elsx_client_restrictions,elsx_rebrand}"
UPGRADE_MODULES="${UPGRADE_MODULES:-website,web_editor,html_editor,html_builder,elsx_client_restrictions,elsx_rebrand}"
DB_NAME_EXCLUDES="${DB_NAME_EXCLUDES:-postgres}"
SKIP_PULL="${SKIP_PULL:-NO}"
SKIP_BUILD="${SKIP_BUILD:-NO}"
ALLOW_BUILD_FALLBACK="${ALLOW_BUILD_FALLBACK:-YES}"

log() {
  printf '[simple-update] %s\n' "$*" >&2
}

quote_csv_for_sql() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/''/g; s/,/','/g")"
}

if [ "${SKIP_PULL}" != "YES" ]; then
  log 'Pulling latest source from origin/main.'
  git pull --ff-only origin main
fi

log 'Ensuring PostgreSQL is running.'
docker compose up -d db

if [ "${SKIP_BUILD}" != "YES" ]; then
  log 'Building and starting services.'
  if ! docker compose up -d --build; then
    if [ "${ALLOW_BUILD_FALLBACK}" = "YES" ]; then
      log 'Build failed. Falling back to existing image plus mounted source; fix Docker/network separately.'
      docker compose up -d db
      docker compose up -d odoo || docker compose restart odoo
    else
      exit 1
    fi
  fi
else
  log 'Skipping image build; restarting Odoo with mounted source.'
  docker compose up -d db
  docker compose restart odoo || docker compose up -d odoo
fi

log 'Detecting application databases.'
EXCLUDE_SQL="$(quote_csv_for_sql "${DB_NAME_EXCLUDES}")"
mapfile -t DATABASES < <(
  docker compose exec -T db sh -lc \
    "psql -U \"\$POSTGRES_USER\" -d postgres -Atc \"SELECT datname FROM pg_database WHERE datistemplate = false AND datallowconn = true AND datname NOT IN (${EXCLUDE_SQL}) ORDER BY datname;\""
)

if [ "${#DATABASES[@]}" -eq 0 ]; then
  log 'No application databases found. Leaving services running.'
  docker compose ps
  exit 0
fi

log "Upgrading modules in ${#DATABASES[@]} database(s): ${DATABASES[*]}"
log "Install-if-missing: ${INSTALL_MODULES}"
log "Upgrade: ${UPGRADE_MODULES}"

log 'Stopping Odoo for clean module upgrade. Sidecar remains running/dormant.'
docker compose stop odoo >/dev/null 2>&1 || true

for DB in "${DATABASES[@]}"; do
  log "Upgrading database: ${DB}"
  docker compose run --rm -T --no-deps odoo \
    python3 /opt/odoo/odoo-bin \
      -d "${DB}" \
      -i "${INSTALL_MODULES}" \
      -u "${UPGRADE_MODULES}" \
      --without-demo=True \
      --stop-after-init \
      --no-http
  log "Finished database: ${DB}"
done

log 'Starting Odoo.'
docker compose up -d odoo

log 'Service status:'
docker compose ps

log 'Done. If browser still shows old UI, hard refresh once: Ctrl+Shift+R.'