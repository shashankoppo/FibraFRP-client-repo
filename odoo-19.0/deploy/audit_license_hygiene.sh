#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> ELSx license hygiene audit"
echo "Root: ${ROOT_DIR}"
echo
echo "This script is read-only. It does not remove or rewrite license files."
echo "Keep required Odoo, third-party, package, and addon manifest license metadata."
echo

echo "==> Required upstream / third-party license candidates"
find "${ROOT_DIR}" \
  \( -path "${ROOT_DIR}/odoo/*" -o -path "${ROOT_DIR}/addons/*" -o -path "${ROOT_DIR}/venv19/*" -o -path "${ROOT_DIR}/node_modules/*" \) \
  \( -iname "LICENSE*" -o -iname "COPYING*" -o -iname "NOTICE*" \) \
  -type f | sort || true

echo
echo "==> Custom addon license files to review for duplication"
find "${ROOT_DIR}/custom_addons" \
  \( -iname "LICENSE*" -o -iname "COPYING*" -o -iname "NOTICE*" \) \
  -type f | sort || true

echo
echo "==> Custom addon manifest license metadata"
find "${ROOT_DIR}/custom_addons" -name "__manifest__.py" -type f -print0 |
while IFS= read -r -d '' manifest; do
  license_line="$(grep -n "['\"]license['\"]" "${manifest}" || true)"
  if [[ -n "${license_line}" ]]; then
    printf "%s: %s\n" "${manifest#${ROOT_DIR}/}" "${license_line}"
  else
    printf "%s: MISSING manifest license key\n" "${manifest#${ROOT_DIR}/}"
  fi
done | sort

echo
echo "==> User-facing license wording in custom docs/static files"
grep -RInE "license|licence|LGPL|AGPL|GPL|Enterprise|copyright" \
  "${ROOT_DIR}/custom_addons" \
  --include="*.md" --include="*.html" --include="*.xml" --include="*.txt" \
  || true

echo
echo "==> Destructive license-removal scripts to delete/avoid"
find "${ROOT_DIR}" -path "${ROOT_DIR}/.git" -prune -o \
  -type f \( -iname "*remove*license*.py" -o -iname "*delete*license*.py" -o -iname "*strip*license*.py" \) \
  -print | sort || true

echo
echo "Review result:"
echo "- Do not delete upstream Odoo or third-party license notices."
echo "- Do not remove manifest license keys; Odoo uses them for module metadata."
echo "- Safe cleanup candidates are duplicate copied license files or confusing custom text that is not legally required."
