#!/usr/bin/env bash
set -euo pipefail

echo "NOTE: this command now upgrades every installed official and custom module."
exec bash deploy/safe_ce19_refresh_all_dbs.sh "$@"
