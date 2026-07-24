#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_DIR"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "$1 is required."
}

require_runtime() {
    require_command docker
    docker info >/dev/null 2>&1 || fail "Docker is not running or this user cannot access it."
    docker compose version >/dev/null 2>&1 || fail "The Docker Compose plugin is required."
    [ -f .env ] || fail "Missing .env. Run: sh server.sh init"

    if grep -Eq '=(replace_with_|change-me)' .env; then
        fail "Replace every placeholder value in .env before starting the server."
    fi

    docker compose config --quiet
}

show_status() {
    echo
    docker compose ps
    echo
    echo "Odoo: http://SERVER_IP:${ODOO_HTTP_PORT:-8069}"
    echo "Database Manager: http://SERVER_IP:${ODOO_HTTP_PORT:-8069}/web/database/manager"
}

confirm_web_backup() {
    if [ "${ODOO_WEB_BACKUP_CONFIRMED:-}" = "YES" ]; then
        return
    fi
    [ -t 0 ] || fail "Set ODOO_WEB_BACKUP_CONFIRMED=YES after downloading an Odoo ZIP backup with filestore."

    echo "Before updating, open /web/database/manager and download a ZIP backup"
    echo "with the filestore included. Keep it outside this Git repository."
    printf "Type BACKUP after verifying the downloaded file: "
    IFS= read -r answer
    [ "$answer" = "BACKUP" ] || fail "Update cancelled. No containers or data were changed."
}

init_environment() {
    [ -f .env.example ] || fail ".env.example is missing."
    if [ -f .env ]; then
        echo ".env already exists. It was not changed."
    else
        cp .env.example .env
        chmod 600 .env 2>/dev/null || true
        echo "Created .env from .env.example."
    fi
    echo "Edit it now and replace every placeholder:"
    echo "    nano .env"
}

start_server() {
    require_runtime
    echo "Building and starting PostgreSQL, Odoo, and the WhatsApp sidecar."
    echo "Named database, filestore, and backup volumes will be preserved."
    docker compose up -d --build
    show_status
}

apply_restored_database() {
    require_runtime
    echo "Applying the current code safely after an Odoo Database Manager restore."
    docker compose stop sidecar >/dev/null 2>&1 || true
    docker compose restart odoo
    docker compose up -d sidecar
    show_status
}

update_server() {
    require_runtime
    require_command git
    confirm_web_backup

    branch=${GIT_BRANCH:-main}
    current_branch=$(git branch --show-current)
    [ "$current_branch" = "$branch" ] || fail "Production must be on branch $branch; current branch is $current_branch."

    if [ -n "$(git status --short --untracked-files=no)" ]; then
        git status --short --untracked-files=no >&2
        fail "Tracked files are modified. Commit or restore them before updating."
    fi

    echo "Pulling origin/$branch with fast-forward protection."
    git pull --ff-only origin "$branch"
    docker compose config --quiet

    echo "Pausing WhatsApp ingress, rebuilding, and applying guarded database upgrades."
    docker compose stop sidecar >/dev/null 2>&1 || true
    docker compose up -d --build
    show_status
}

show_help() {
    cat <<'EOF'
Simple Odoo server commands

  sh server.sh init     Create .env without overwriting an existing one
  sh server.sh start    Build and start a new or existing server
  sh server.sh apply    Apply code after restoring a ZIP in Database Manager
  sh server.sh update   Confirm web backup, pull main, build, and update safely
  sh server.sh status   Show container status
  sh server.sh logs     Show recent Odoo and WhatsApp logs

Never use `docker compose down -v`; it deletes named client-data volumes.
EOF
}

case "${1:-help}" in
    init)
        init_environment
        ;;
    start)
        start_server
        ;;
    apply)
        apply_restored_database
        ;;
    update)
        update_server
        ;;
    status)
        require_runtime
        show_status
        ;;
    logs)
        require_runtime
        docker compose logs --tail="${LOG_LINES:-200}" odoo sidecar
        ;;
    help|-h|--help)
        show_help
        ;;
    *)
        show_help >&2
        exit 2
        ;;
esac
