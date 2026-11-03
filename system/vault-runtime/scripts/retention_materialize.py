#!/usr/bin/env python3
"""Materialize exact retention manifests and their required supplemental files.

Only brctl download requests mutate local availability. Source content, names,
permissions and timestamps are never written. Vault archives are not needed for
the retention inventory; their restoration remains a separate verification.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "retention-source-materialization/v1"
DATALESS = getattr(stat, "UF_DATALESS", 0x40000000)


def is_dataless(path: Path) -> bool:
    return bool(getattr(path.stat(), "st_flags", 0) & DATALESS)


def exact_file(path: Path, directory: Path) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("absolute_non_symlink_file_required")
    if path.resolve().parent != directory or not path.is_file():
        raise ValueError("file_must_exist_directly_inside_backup_directory")
    return path.resolve()


def digest(path: Path) -> str:
    if is_dataless(path):
        raise ValueError("source_became_dataless_before_read")
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def request_download(path: Path) -> dict[str, object] | None:
    try:
        result = subprocess.run(
            ["/usr/bin/brctl", "download", str(path)],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode:
            return {"path": str(path), "exit_code": result.returncode,
                    "error": result.stderr.strip()[:300]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"path": str(path), "error": str(error)}
    return None


def supplemental_binding(payload: dict, manifest: Path, directory: Path) -> dict | None:
    if payload.get("schema") in {"vault-backup/v1", "vault-backup/v2"}:
        return None
    if payload.get("schema") is not None:
        raise ValueError("unknown_backup_schema")
    if payload.get("trigger") == "manual-user-clarification":
        key, sha_key = "backup", "sha256_before"
    elif manifest.name.startswith("semantic-index-prechange-"):
        key, sha_key = "archive", "archive_sha256"
    else:
        raise ValueError("unknown_backup_manifest_format")
    path = exact_file(Path(str(payload[key])), directory)
    expected = str(payload[sha_key])
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("invalid_backup_digest")
    return {"manifest": str(manifest), "path": str(path), "sha256": expected}


def materialize(directory: Path, apply: bool, timeout: float, poll: float = 15) -> dict:
    started = time.monotonic()
    directory = directory.resolve()
    errors: list[dict] = []
    request_errors: list[dict] = []
    requested: list[str] = []
    remaining: list[str] = []
    records: dict[str, dict] = {}
    bindings: list[dict] = []
    manifests = sorted(directory.glob("*.manifest.json")) if directory.is_dir() else []
    initial_names = {str(p) for p in manifests}

    def remember(path: Path) -> None:
        if str(path) in records:
            return
        info = path.stat()
        dataless = is_dataless(path)
        records[str(path)] = {"initial_dataless": dataless, "bytes": info.st_size,
                              "mode_before": oct(info.st_mode & 0o777),
                              "sha256_before": None if dataless else digest(path)}

    def hydrate(paths: list[Path]) -> bool:
        nonlocal remaining
        for p in paths:
            remember(p)
        pending = [p for p in paths if is_dataless(p)]
        if pending and apply:
            if sys.platform != "darwin" or not Path("/usr/bin/brctl").is_file():
                errors.append({"reason": "macos_brctl_required"})
            else:
                requested.extend(str(p) for p in pending)
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                    request_errors.extend(e for e in executor.map(request_download, pending) if e)
                while pending:
                    pending = [p for p in paths if is_dataless(p)]
                    left = timeout - (time.monotonic() - started)
                    if not pending or left <= 0:
                        break
                    print(f"retention materialize: {len(pending)} pending", file=sys.stderr, flush=True)
                    time.sleep(min(poll, left))
        remaining = [str(p) for p in paths if is_dataless(p)]
        return not remaining

    try:
        if not directory.is_dir():
            raise ValueError("backup_directory_missing")
        if not manifests:
            raise ValueError("backup_manifests_missing")
        manifests = [exact_file(p, directory) for p in manifests]
        # Never open any manifests until the full manifest inventory is local.
        if hydrate(manifests):
            for p in manifests:
                if is_dataless(p):
                    raise ValueError("manifest_became_dataless_before_read")
                payload = json.loads(p.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("backup_manifest_object_required")
                binding = supplemental_binding(payload, p, directory)
                if binding:
                    bindings.append(binding)
            dependencies = sorted({Path(b["path"]) for b in bindings})
            if hydrate(dependencies):
                for binding in bindings:
                    if digest(Path(binding["path"])) != binding["sha256"]:
                        errors.append({"path": binding["path"], "manifest": binding["manifest"],
                                       "reason": "supplemental_backup_sha256_mismatch"})
        # Recheck all declared files, not merely the final download batch.
        remaining = [name for name in records if is_dataless(Path(name))]
        for name, record in records.items():
            p = exact_file(Path(name), directory)
            if str(p) in remaining:
                continue
            record["sha256_after"] = digest(p)
            record["mode_after"] = oct(p.stat().st_mode & 0o777)
            if record["sha256_before"] and record["sha256_before"] != record["sha256_after"]:
                errors.append({"path": name, "reason": "source_content_changed_during_materialization"})
            if record["mode_before"] != record["mode_after"]:
                errors.append({"path": name, "reason": "source_permissions_changed_during_materialization"})
        if {str(p) for p in directory.glob("*.manifest.json")} != initial_names:
            errors.append({"reason": "backup_manifest_inventory_changed"})
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError) as error:
        errors.append({"reason": str(error)})
    blockers = (["retention_sources_not_materialized"] if remaining else [])
    if errors:
        blockers.append("retention_source_inventory_or_integrity_failed")
    return {"schema": SCHEMA, "observed_at": datetime.now(timezone.utc).isoformat(),
            "backup_dir": str(directory), "apply": apply, "content_write": False,
            "manifest_count": len(manifests), "supplemental_bindings": bindings,
            "requested_count": len(requested), "requested_paths": requested,
            "remaining_count": len(remaining), "remaining_paths": remaining,
            "request_errors": request_errors, "errors": errors, "source_readback": records,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "level": "blocked" if blockers else "verified-working", "blockers": blockers,
            "scope_boundary": "Only direct manifests and required same-directory supplemental files; no live source or historical vault archive hydration."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--poll-seconds", type=float, default=15)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.timeout_seconds < 0 or args.poll_seconds <= 0:
        parser.error("timeout must be nonnegative and poll must be positive")
    payload = materialize(args.backup_dir.expanduser(), args.apply,
                          args.timeout_seconds, args.poll_seconds)
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["level"])
    return 0 if not payload["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
