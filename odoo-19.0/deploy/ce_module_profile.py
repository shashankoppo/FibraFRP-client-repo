#!/usr/bin/env python3
"""Print an auditable Odoo CE application/localization module profile."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOTS = (PROJECT_ROOT / "addons", PROJECT_ROOT / "odoo" / "addons")
COUNTRY_EXTRAS = {
    "IN": {"payment_payu"},
    "KR": {"payment_toss_payments"},
    "TW": {"payment_ecpay"},
}


def iter_manifests():
    for addon_root in ADDON_ROOTS:
        for manifest_path in sorted(addon_root.glob("*/__manifest__.py")):
            module_name = manifest_path.parent.name
            try:
                manifest = ast.literal_eval(
                    manifest_path.read_text(encoding="utf-8-sig")
                )
            except (OSError, SyntaxError, ValueError) as exc:
                raise SystemExit(f"Cannot parse {manifest_path}: {exc}") from exc
            if manifest.get("installable", True):
                yield module_name, manifest


def build_profile(include_applications: bool, countries: list[str]) -> list[str]:
    manifests = dict(iter_manifests())
    selected: set[str] = set()

    if include_applications:
        selected.update(
            module_name
            for module_name, manifest in manifests.items()
            if manifest.get("application")
            and not module_name.startswith(("l10n_", "test_", "theme_"))
        )

    for country in countries:
        country_code = country.upper()
        selected.update(
            module_name
            for module_name, manifest in manifests.items()
            if module_name.startswith("l10n_")
            and country_code.lower()
            in {str(code).lower() for code in manifest.get("countries", [])}
        )
        selected.update(
            module_name
            for module_name in COUNTRY_EXTRAS.get(country_code, set())
            if module_name in manifests
        )

    return sorted(selected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--applications",
        action="store_true",
        help="include every installable official CE module marked application=True",
    )
    parser.add_argument(
        "--country",
        action="append",
        default=[],
        help="include official CE localization modules for this ISO country code",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "lines"),
        default="csv",
    )
    args = parser.parse_args()

    modules = build_profile(args.applications, args.country)
    print(",".join(modules) if args.format == "csv" else "\n".join(modules))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
