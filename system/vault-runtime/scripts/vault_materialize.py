#!/usr/bin/env python3
"""Materialize only files selected for a vault operation; never rewrite content."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DATALESS_FLAG = 0x40000000
SKIP = {".git", ".trash", "_trash", "_export", "outputs", "__pycache__"}
ESSENTIAL = {"outputs/vault-status.json", "outputs/automation-runs.jsonl"}


def selected_files(vault: Path, scope: str) -> list[Path]:
    if scope != "maintenance":
        from vault_health import SCOPE_PROFILES, iter_markdown

        return sorted(p for p in iter_markdown(vault, SCOPE_PROFILES[scope]) if not p.is_symlink())
    result = []
    for path in vault.rglob("*"):
        relative = path.relative_to(vault)
        if path.is_symlink() or not path.is_file():
            continue
        if any(part in SKIP for part in relative.parts) and relative.as_posix() not in ESSENTIAL:
            continue
        result.append(path)
    return sorted(result)


def is_dataless(path: Path) -> bool:
    return bool(getattr(path.stat(), "st_flags", 0) & DATALESS_FLAG)


def request_download(path: Path) -> dict[str, object] | None:
    try:
        result = subprocess.run(
            ["/usr/bin/brctl", "download", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode:
            return {"path": str(path), "exit_code": result.returncode, "error": result.stderr.strip()[:300]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"path": str(path), "error": str(error)}
    return None


def materialize(vault: Path, scope: str, apply: bool, timeout: float) -> dict[str, object]:
    started = time.monotonic()
    files = selected_files(vault, scope)
    pending = [path for path in files if is_dataless(path)]
    original_count = len(pending)
    errors: list[dict[str, object]] = []
    if apply and pending:
        if sys.platform != "darwin" or not Path("/usr/bin/brctl").is_file():
            errors.append({"error": "macos_brctl_required_for_dataless_files"})
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                errors.extend(error for error in executor.map(request_download, pending) if error)
            while pending:
                pending = [path for path in pending if is_dataless(path)]
                if not pending or time.monotonic() - started >= timeout:
                    break
                print(f"materialize: {len(pending)}/{original_count} pending", file=sys.stderr, flush=True)
                time.sleep(min(5, max(0.0, timeout - (time.monotonic() - started))))
    # Recheck the complete selected set: an already-local file may have been evicted.
    remaining = [path.relative_to(vault).as_posix() for path in files if is_dataless(path)]
    return {
        "schema": "vault-materialization/v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "vault": str(vault),
        "scope": scope,
        "apply": apply,
        "content_write": False,
        "files_selected": len(files),
        "initial_dataless": original_count,
        "download_requests": original_count if apply and not (errors and errors[0].get("error") == "macos_brctl_required_for_dataless_files") else 0,
        "remaining_count": len(remaining),
        "remaining_paths": remaining,
        "request_errors": errors,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "level": "verified-working" if not remaining else "blocked",
        "blockers": ["selected_files_not_materialized"] if remaining else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=".")
    parser.add_argument("--scope", choices=["maintenance", "core", "knowledge", "all"], default="maintenance")
    parser.add_argument("--apply", action="store_true", help="Request exact pending files from iCloud; never rewrite note content")
    parser.add_argument("--timeout-seconds", type=float, default=1200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    vault = Path(args.path).expanduser().resolve()
    if not vault.is_dir() or args.timeout_seconds < 0:
        parser.error("vault must exist and timeout must be nonnegative")
    payload = materialize(vault, args.scope, args.apply, args.timeout_seconds)
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["level"])
    return 0 if not payload["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
