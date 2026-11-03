#!/usr/bin/env python3
"""Audit backup, automation, and status retention evidence without deleting anything."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "second-brain-retention-audit/v1"


class BackupSourceUnavailable(OSError):
    def __init__(self, source: dict[str, str]) -> None:
        self.source = source
        super().__init__(f"{source['reason']}:{source['path']}")


def unavailable_source(path: Path) -> dict[str, str] | None:
    """Inspect metadata only; never follow a source symlink or open a placeholder."""
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            return {"path": str(path), "reason": "symlink"}
        if not stat.S_ISREG(metadata.st_mode):
            return {"path": str(path), "reason": "not_regular_file"}
        if getattr(metadata, "st_flags", 0) & getattr(stat, "UF_DATALESS", 0x40000000):
            return {"path": str(path), "reason": "dataless"}
    except OSError as error:
        return {"path": str(path), "reason": f"stat_failed:{error.errno}"}
    return None


def require_available_source(path: Path) -> None:
    source = unavailable_source(path)
    if source:
        raise BackupSourceUnavailable(source)


def unavailable_backup_sources(directory: Path) -> list[dict[str, str]]:
    """Preflight manifests, then only known, directory-bound supplemental files."""
    manifests = sorted(directory.glob("*.manifest.json"))
    unavailable = [source for manifest in manifests if (source := unavailable_source(manifest))]
    if unavailable:
        return unavailable
    for manifest in manifests:
        try:
            require_available_source(manifest)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except BackupSourceUnavailable as error:
            unavailable.append(error.source)
            continue
        except OSError as error:
            unavailable.append({"path": str(manifest), "reason": f"read_failed:{error.errno}"})
            continue
        except (ValueError, json.JSONDecodeError):
            continue  # The inventory loader reports malformed manifests as invalid.
        if not isinstance(payload, dict) or payload.get("schema") is not None:
            continue
        try:
            supplemental_backup(payload, manifest, directory, verify_content=False)
        except BackupSourceUnavailable as error:
            unavailable.append(error.source)
        except (OSError, KeyError, TypeError, ValueError):
            pass  # Invalid or unbound references must still fail the inventory loader.
    return unavailable


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include timezone")
    return parsed.astimezone(timezone.utc)


def local_backup_path(payload: dict[str, object], directory: Path, key: str, digest_key: str) -> Path:
    backup = Path(str(payload[key]))
    digest = str(payload[digest_key])
    if not backup.is_absolute() or backup.is_symlink() or backup.resolve().parent != directory.resolve():
        raise ValueError("supplemental_backup_outside_directory")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("supplemental_backup_metadata_invalid")
    require_available_source(backup)
    if not backup.is_file():
        raise ValueError("supplemental_backup_metadata_invalid")
    return backup


def verified_local_backup(payload: dict[str, object], directory: Path, key: str, digest_key: str) -> Path:
    backup = local_backup_path(payload, directory, key, digest_key)
    require_available_source(backup)
    if hashlib.sha256(backup.read_bytes()).hexdigest() != str(payload[digest_key]):
        raise ValueError("supplemental_backup_sha256_mismatch")
    return backup


def supplemental_backup(
    payload: dict[str, object], manifest: Path, directory: Path, *, verify_content: bool = True,
) -> dict[str, object]:
    """Validate known legacy receipts separately; they do not satisfy vault retention."""
    backup_path = verified_local_backup if verify_content else local_backup_path
    if payload.get("schema") is not None:
        raise ValueError("unknown_backup_schema")
    if payload.get("trigger") == "manual-user-clarification":
        target = Path(str(payload["target"]))
        if (not target.is_absolute() or target.name != "memory.md"
                or target.parent.parent.name != "automations"
                or target.parent.parent.parent.name != ".codex"):
            raise ValueError("automation_memory_target_invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", str(payload["sha256_after"])):
            raise ValueError("automation_memory_after_digest_invalid")
        if not payload.get("change") or not payload.get("readback"):
            raise ValueError("automation_memory_receipt_incomplete")
        recorded_at = parse_time(str(payload["recorded_at"]))
        backup = backup_path(payload, directory, "backup", "sha256_before")
        return {"kind": "automation-memory-backup", "manifest": manifest.name,
                "recorded_at": recorded_at.isoformat(), "backup": str(backup),
                "backup_sha256_verified": verify_content, "legacy_format": True,
                "historical_readback_claim": payload["readback"],
                "current_live_target_verified": False}
    if manifest.name.startswith("semantic-index-prechange-"):
        files = payload["files"]
        if not isinstance(files, dict) or not files:
            raise ValueError("semantic_index_files_missing")
        for source, entry in files.items():
            parts = Path(source).parts
            if (not Path(source).is_absolute() or len(parts) < 4
                    or parts[-4:-2] != ("qwen3-search", "indexes")
                    or parts[-2] not in {"core", "knowledge"}
                    or parts[-1] not in {"metadata.json", "vectors.npy"}
                    or not isinstance(entry, dict)
                    or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", "")))
                    or not isinstance(entry.get("bytes"), int) or entry["bytes"] < 0):
                raise ValueError("semantic_index_file_metadata_invalid")
        created_at = parse_time(str(payload["created_at"]))
        archive = backup_path(payload, directory, "archive", "archive_sha256")
        return {"kind": "semantic-index-backup", "manifest": manifest.name,
                "created_at": created_at.isoformat(), "archive": str(archive),
                "archive_sha256_verified": verify_content, "source_file_count": len(files),
                "legacy_format": True, "current_live_indexes_verified": False}
    raise ValueError("unknown_backup_manifest_format")


def load_backup_times(directory: Path) -> tuple[list[datetime], list[str], list[dict[str, object]]]:
    times: list[datetime] = []
    errors: list[str] = []
    supplemental: list[dict[str, object]] = []
    if not directory.is_dir():
        return times, ["backup_directory_missing"], supplemental
    for manifest in sorted(directory.glob("*.manifest.json")):
        try:
            require_available_source(manifest)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("backup_manifest_object_required")
            if payload.get("schema") in {"vault-backup/v1", "vault-backup/v2"}:
                times.append(parse_time(str(payload["created_at"])))
            else:
                supplemental.append(supplemental_backup(payload, manifest, directory))
        except BackupSourceUnavailable:
            raise
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            errors.append(f"invalid_backup_manifest:{manifest.name}")
    return times, errors, supplemental


def load_scheduled_runs(ledger: Path) -> tuple[list[datetime], list[str]]:
    runs: list[datetime] = []
    errors: list[str] = []
    if not ledger.is_file():
        return runs, ["automation_ledger_missing"]
    for number, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if record.get("schema") != "automation-run-provenance/v1":
                raise ValueError("schema")
            if record.get("trigger") == "scheduled":
                runs.append(parse_time(str(record["finished_at"])))
        except (ValueError, KeyError, json.JSONDecodeError):
            errors.append(f"invalid_automation_record:{number}")
    return runs, errors


def audit(
    policy: dict[str, object],
    backup_dir: Path,
    ledger: Path,
    status_manifest: Path,
    now: datetime,
) -> dict[str, object]:
    blockers: list[str] = []
    unavailable = unavailable_backup_sources(backup_dir)
    # A partial inventory cannot establish retention counts. Do not open any
    # manifests when known placeholders would make the whole inventory incomplete.
    if unavailable:
        backup_times, backup_errors, supplemental_backups = [], ["backup_sources_unavailable"], []
    else:
        try:
            backup_times, backup_errors, supplemental_backups = load_backup_times(backup_dir)
        except BackupSourceUnavailable as error:
            # A source may be evicted after preflight. Discard any partial count.
            unavailable.append(error.source)
            backup_times, backup_errors, supplemental_backups = [], ["backup_sources_unavailable"], []
    blockers.extend(backup_errors)
    backup_policy = policy["backups"]
    minimum_backups = int(backup_policy["minimum_retained"])
    if not unavailable and len(backup_times) < minimum_backups:
        blockers.append("backup_minimum_not_met")
    latest_backup = max(backup_times) if backup_times else None
    if latest_backup and (now - latest_backup).total_seconds() > int(backup_policy["max_latest_age_days"]) * 86400:
        blockers.append("latest_backup_too_old")

    scheduled_runs, ledger_errors = load_scheduled_runs(ledger)
    blockers.extend(ledger_errors)
    automation_policy = policy["automation_provenance"]
    if len(scheduled_runs) < int(automation_policy["minimum_scheduled_runs"]):
        blockers.append("scheduled_run_evidence_missing")
    latest_scheduled = max(scheduled_runs) if scheduled_runs else None
    if latest_scheduled and (now - latest_scheduled).total_seconds() > int(automation_policy["max_latest_scheduled_age_days"]) * 86400:
        blockers.append("latest_scheduled_run_too_old")

    status_valid_until: datetime | None = None
    if not status_manifest.is_file():
        blockers.append("status_manifest_missing")
    else:
        try:
            status = json.loads(status_manifest.read_text(encoding="utf-8"))
            status_valid_until = parse_time(str(status["valid_until"]))
            if bool(policy["status_manifest"]["must_be_unexpired"]) and now >= status_valid_until:
                blockers.append("status_manifest_expired")
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            blockers.append("status_manifest_invalid")

    blockers = sorted(set(blockers))
    return {
        "schema": SCHEMA,
        "observed_at": now.isoformat(),
        "level": "blocked" if unavailable else ("verified-working" if not blockers else "degraded"),
        "blockers": blockers,
        "backups": {
            "verified": not unavailable and not backup_errors,
            "unavailable_sources": unavailable,
            "count": None if unavailable else len(backup_times),
            "latest": latest_backup.isoformat() if latest_backup else None,
            "minimum_retained": minimum_backups,
            "target_retained": int(backup_policy.get("target_retained", minimum_backups)),
            "target_gap": None if unavailable else max(0, int(backup_policy.get("target_retained", minimum_backups)) - len(backup_times)),
        },
        "supplemental_backups": {
            "count": None if unavailable else len(supplemental_backups),
            "receipts": supplemental_backups,
            "counts_toward_vault_retention": False,
        },
        "automation": {
            "scheduled_run_count": len(scheduled_runs),
            "latest_scheduled": latest_scheduled.isoformat() if latest_scheduled else None,
        },
        "status": {
            "valid_until": status_valid_until.isoformat() if status_valid_until else None,
        },
        "safety": {
            "delete_count": 0,
            "mutates_artifacts": False,
            "policy": "Audit only; retention candidates require explicit approval before deletion or archival.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--status-manifest", required=True)
    parser.add_argument("--now")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        policy = json.loads(Path(args.policy).expanduser().read_text(encoding="utf-8"))
        now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
        payload = audit(
            policy,
            Path(args.backup_dir).expanduser().resolve(),
            Path(args.ledger).expanduser().resolve(),
            Path(args.status_manifest).expanduser().resolve(),
            now,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["level"])
        return 0 if not payload["blockers"] else 1
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"schema": SCHEMA, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
