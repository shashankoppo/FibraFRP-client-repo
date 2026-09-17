#!/usr/bin/env bash
set -euo pipefail
command -v python3 >/dev/null || { echo 'Install Python 3: apk add python3 (Alpine) or apt-get install python3 (Ubuntu).' >&2; exit 1; }
cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 deploy/client_deploy.py production "$@"
