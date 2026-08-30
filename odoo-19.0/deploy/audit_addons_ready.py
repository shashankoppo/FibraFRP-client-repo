#!/usr/bin/env python3
"""Check addon discoverability and manifest dependencies for this deployment."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


DEFAULT_ADDONS_PATH = (
    "addons",
    "odoo/addons",
    "custom_addons",
    "custom_addons/elsx_stubs",
    "third_party_addons",
)


def read_manifest(path: Path) -> dict:
    try:
        value = ast.literal_eval(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report exact manifest path.
        raise ValueError(f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: manifest must be a Python dict")
    return value


def addon_roots(project_root: Path, paths_csv: str | None) -> list[Path]:
    raw_paths = paths_csv.split(",") if paths_csv else list(DEFAULT_ADDONS_PATH)
    roots: list[Path] = []
    for raw_path in raw_paths:
        raw_path = raw_path.strip()
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = project_root / path
        roots.append(path.resolve())
    return roots


def split_csv(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def iter_immediate_modules(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path.parent.resolve() for path in root.glob("*/__manifest__.py"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit custom and third-party Odoo addons before install/update."
    )
    parser.add_argument(
        "--addons-path",
        help="Comma-separated addon roots. Defaults to this repo's Docker/local paths.",
    )
    parser.add_argument(
        "--installed-modules",
        help="Comma-separated module names installed in a database.",
    )
    parser.add_argument(
        "--target-modules",
        help="Comma-separated module names that will be upgraded.",
    )
    parser.add_argument(
        "--require-installed-dependencies",
        action="store_true",
        help="Fail if target module manifests depend on modules not already installed.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    roots = addon_roots(project_root, args.addons_path)
    module_dirs: dict[str, Path] = {}
    manifest_errors: list[str] = []

    for root in roots:
        for module_dir in iter_immediate_modules(root):
            manifest = module_dir / "__manifest__.py"
            try:
                data = read_manifest(manifest)
            except ValueError as exc:
                manifest_errors.append(str(exc))
                continue
            module_dirs[module_dir.name] = module_dir
            data.setdefault("depends", [])

    known_modules = set(module_dirs)
    missing_dependencies: list[str] = []
    for module, module_dir in sorted(module_dirs.items()):
        data = read_manifest(module_dir / "__manifest__.py")
        for dependency in data.get("depends", []):
            if dependency not in known_modules:
                missing_dependencies.append(
                    f"{module} depends on missing addon {dependency!r}"
                )

    missing_installed_dependencies: list[str] = []
    if args.require_installed_dependencies:
        installed_modules = split_csv(args.installed_modules)
        target_modules = split_csv(args.target_modules) or installed_modules
        for module in sorted(target_modules):
            module_dir = module_dirs.get(module)
            if not module_dir:
                missing_installed_dependencies.append(
                    f"{module} is targeted for upgrade but is not reachable from addons_path"
                )
                continue
            data = read_manifest(module_dir / "__manifest__.py")
            for dependency in data.get("depends", []):
                if dependency not in installed_modules:
                    missing_installed_dependencies.append(
                        f"{module} depends on {dependency!r}, but it is not installed"
                    )

    checked_collections = [
        project_root / "custom_addons",
        project_root / "third_party_addons",
    ]
    discoverable_dirs = set(module_dirs.values())
    hidden_manifests = []
    for collection in checked_collections:
        if collection.exists():
            hidden_manifests.extend(
                manifest.parent.resolve()
                for manifest in collection.rglob("__manifest__.py")
                if manifest.parent.resolve() not in discoverable_dirs
            )

    print("Addon roots:")
    for root in roots:
        state = "ok" if root.exists() else "missing"
        print(f"  - {root.relative_to(project_root) if root.is_relative_to(project_root) else root} ({state})")
    print(f"Discoverable modules: {len(module_dirs)}")

    if hidden_manifests:
        print("\nManifests not reachable from addons_path:")
        for path in sorted(hidden_manifests):
            rel = path.relative_to(project_root) if path.is_relative_to(project_root) else path
            print(f"  - {rel}")

    if manifest_errors:
        print("\nManifest parse errors:")
        for error in manifest_errors:
            print(f"  - {error}")

    if missing_dependencies:
        print("\nMissing dependencies:")
        for issue in missing_dependencies:
            print(f"  - {issue}")

    if missing_installed_dependencies:
        print("\nDependencies that would require installing new modules:")
        for issue in missing_installed_dependencies:
            print(f"  - {issue}")

    if (
        hidden_manifests
        or manifest_errors
        or missing_dependencies
        or missing_installed_dependencies
    ):
        return 1

    print("Addon audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
