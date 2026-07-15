#!/bin/sh
set -eu

# Read-only Docker host verification for Ubuntu and Alpine hosts.
# This script does not start, stop, restart, install, upgrade, delete, or write
# client database data. It only validates host prerequisites, compose syntax,
# and optionally reachable health endpoints.

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_DIR"

VERIFY_RUNNING=${VERIFY_RUNNING:-1}
REQUIRE_SIDECAR=${REQUIRE_SIDECAR:-0}
COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.prod.yml}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

warn() {
  echo "WARN: $*" >&2
}

have() {
  command -v "$1" >/dev/null 2>&1
}

http_ok() {
  url=$1
  if have curl; then
    curl -fsS "$url" >/dev/null
  elif have wget; then
    wget -q -O /dev/null "$url"
  else
    return 2
  fi
}

echo "== FiberaFRP Docker host verification =="

OS_ID=unknown
OS_VERSION=unknown
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  OS_ID=${ID:-unknown}
  OS_VERSION=${VERSION_ID:-unknown}
fi
echo "Host OS: $OS_ID $OS_VERSION"

case "$OS_ID" in
  ubuntu)
    echo "Ubuntu host detected."
    ;;
  alpine)
    echo "Alpine host detected."
    if ! have bash; then
      warn "bash is not installed. Runtime compose works, but existing deploy/*.sh maintenance scripts require bash."
    fi
    warn "If this is a Proxmox LXC host, run: sh deploy/verify_alpine_docker_runtime.sh"
    ;;
  *)
    warn "Host is not Ubuntu or Alpine. Continuing with generic Docker checks."
    ;;
esac

have docker || fail "docker CLI is not installed or not in PATH."
docker info >/dev/null 2>&1 || fail "docker daemon is not reachable by this user."
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is not available."

echo "-- Docker"
docker --version
docker compose version

[ -f "$COMPOSE_FILE" ] || fail "$COMPOSE_FILE not found."

echo "-- Compose syntax"
docker compose -f "$COMPOSE_FILE" config --quiet
echo "$COMPOSE_FILE config OK"

if [ -f docker-compose.yml ]; then
  docker compose -f docker-compose.yml config --quiet
  echo "docker-compose.yml config OK"
fi

if [ -f docker-compose.alpine-lxc.yml ]; then
  docker compose -f docker-compose.alpine-lxc.yml config --quiet
  echo "docker-compose.alpine-lxc.yml config OK"
fi

echo "-- Data volume declaration"
docker compose -f "$COMPOSE_FILE" config | grep -E "odoo-db-data:|odoo-web-data:" >/dev/null \
  || fail "required database/filestore volumes are not declared."
echo "Named database and filestore volumes are declared."

if [ "$VERIFY_RUNNING" = "1" ]; then
  echo "-- Running service status"
  docker compose -f "$COMPOSE_FILE" ps || true

  echo "-- Odoo health"
  if http_ok "http://127.0.0.1:${ODOO_HTTP_PORT:-8069}/web/health"; then
    echo "Odoo health OK"
  else
    fail "Odoo health endpoint is not reachable."
  fi

  echo "-- WhatsApp sidecar health"
  if http_ok "http://127.0.0.1:${SIDECAR_HTTP_PORT:-3000}/health"; then
    echo "WhatsApp sidecar health OK"
  elif [ "$REQUIRE_SIDECAR" = "1" ]; then
    fail "WhatsApp sidecar is required but not reachable."
  else
    warn "WhatsApp sidecar is not reachable. Set REQUIRE_SIDECAR=1 to make this fatal."
  fi
else
  echo "-- Running health checks skipped (VERIFY_RUNNING=0)"
fi

echo "Verification complete."