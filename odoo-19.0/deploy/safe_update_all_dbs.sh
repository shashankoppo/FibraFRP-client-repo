#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "NOTE: safe_update_all_dbs.sh now runs the complete CE 19 refresh workflow."
exec bash "${SCRIPT_DIR}/safe_ce19_refresh_all_dbs.sh" "$@"
