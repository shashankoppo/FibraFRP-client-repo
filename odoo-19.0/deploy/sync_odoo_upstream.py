#!/usr/bin/env python3
"""Synchronize the allowlisted Odoo CE tree from an exact audited commit."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = PROJECT_ROOT / "ODOO_UPSTREAM.lock"


class SyncError(RuntimeError):
    pass


def run_git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise SyncError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def load_lock() -> dict:
    try:
        lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"Cannot read {LOCK_PATH}: {exc}") from exc
    if lock.get("schema_version") != 1:
        raise SyncError("Unsupported ODOO_UPSTREAM.lock schema.")
    return lock


def validate_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise SyncError(f"Unsafe allowlisted path: {value!r}")
    return path


def validate_source(source: Path, lock: dict) -> None:
    if not source.is_dir():
        raise SyncError(f"Source checkout does not exist: {source}")
    if PROJECT_ROOT == source or PROJECT_ROOT in source.parents or source in PROJECT_ROOT.parents:
        raise SyncError("The upstream checkout must be separate from the project tree.")

    actual_commit = run_git("rev-parse", "HEAD", cwd=source)
    expected_commit = lock["target_commit"]
    if actual_commit != expected_commit:
        raise SyncError(
            f"Upstream checkout is {actual_commit}; expected pinned commit {expected_commit}."
        )
    if run_git("status", "--porcelain", "--untracked-files=no", cwd=source):
        raise SyncError("Upstream checkout has tracked modifications.")

    release_file = source / "odoo" / "release.py"
    release_text = release_file.read_text(encoding="utf-8")
    if "version_info = (19, 0," not in release_text:
        raise SyncError("Pinned source is not Odoo CE 19.0.")
    if (source / "enterprise").exists():
        raise SyncError("Enterprise source must not be present in the CE synchronization checkout.")


def owned_paths(lock: dict) -> list[Path]:
    paths = [
        validate_relative_path(value)
        for value in lock.get("owned_directories", []) + lock.get("owned_files", [])
    ]
    if not paths:
        raise SyncError("The upstream allowlist is empty.")
    return paths


def ensure_clean_owned_tree(paths: list[Path]) -> None:
    output = run_git(
        "status",
        "--porcelain",
        "--untracked-files=no",
        "--",
        *(path.as_posix() for path in paths),
        cwd=PROJECT_ROOT,
    )
    if output:
        raise SyncError(
            "Tracked upstream-owned paths are dirty; commit or restore them before syncing:\n"
            + output
        )


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(root: Path, paths: list[Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in paths:
        path = root / relative
        if not path.exists():
            raise SyncError(f"Allowlisted source path is missing: {path}")
        if path.is_dir():
            for file_path in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
                key = file_path.relative_to(root).as_posix()
                result[key] = file_digest(file_path)
        else:
            result[relative.as_posix()] = file_digest(path)
    return result


def compare(source: Path, paths: list[Path]) -> tuple[int, list[str]]:
    source_inventory = inventory(source, paths)
    target_inventory = inventory(PROJECT_ROOT, paths)
    all_files = sorted(source_inventory.keys() | target_inventory.keys())
    differences = [
        path
        for path in all_files
        if source_inventory.get(path) != target_inventory.get(path)
    ]
    return len(source_inventory), differences


def apply_sync(source: Path, paths: list[Path]) -> None:
    ensure_clean_owned_tree(paths)
    for relative in paths:
        source_path = source / relative
        target_path = PROJECT_ROOT / relative
        if source_path.is_dir():
            if target_path.exists():
                shutil.rmtree(target_path)
            shutil.copytree(source_path, target_path, symlinks=True)
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Clean official Odoo checkout at the exact commit in ODOO_UPSTREAM.lock.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the synchronization. Without this flag, only compare trees.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    try:
        lock = load_lock()
        paths = owned_paths(lock)
        validate_source(source, lock)
        source_count, differences = compare(source, paths)
        if not args.apply:
            print(
                f"Pinned Odoo source contains {source_count} allowlisted files; "
                f"{len(differences)} differ from the project tree."
            )
            return 1 if differences else 0

        if not differences:
            print("Project already matches the pinned Odoo source.")
            return 0
        print(f"Synchronizing {len(differences)} differing allowlisted files.")
        apply_sync(source, paths)
        verified_count, remaining = compare(source, paths)
        if remaining:
            raise SyncError(
                f"Post-sync verification failed for {len(remaining)} allowlisted files."
            )
        print(f"Verified {verified_count} pinned Odoo CE 19.0 files.")
        return 0
    except (OSError, SyncError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
