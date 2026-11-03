#!/usr/bin/env python3
"""Create immutable vault snapshots and verify restoration in a separate directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "vault-backup/v2"
SKIP = {".git", ".trash", "_trash", "_export", "outputs", "__pycache__"}
ESSENTIAL_RUNTIME_FILES = {
    "outputs/vault-status.json",
    "outputs/automation-runs.jsonl",
}
EXTERNAL_LABEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SNAPSHOT_MODE = 0o400


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_map(root: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        relative_text = relative.as_posix()
        if path.is_symlink():
            raise ValueError(f"symlink_not_supported:{relative_text}")
        if not path.is_file():
            continue
        if any(part in SKIP for part in relative.parts) and relative_text not in ESSENTIAL_RUNTIME_FILES:
            continue
        rows[relative_text] = sha256(path)
    return rows


def all_file_map(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def seal_read_only(file_descriptor: int) -> None:
    """Set and verify owner-only read access before publishing a backup file."""
    os.fchmod(file_descriptor, SNAPSHOT_MODE)
    if stat.S_IMODE(os.fstat(file_descriptor).st_mode) != SNAPSHOT_MODE:
        raise OSError("backup_mode_readback_failed:expected_0400")
    os.fsync(file_descriptor)


def backup_file_modes(archive: Path, manifest: Path) -> dict[str, str | None]:
    return {
        name: f"{stat.S_IMODE(path.stat().st_mode):04o}" if path.is_file() else None
        for name, path in (("archive", archive), ("manifest", manifest))
    }


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as temp:
            temporary_path = Path(temp.name)
            temp.write(encoded)
            temp.flush()
            seal_read_only(temp.fileno())
        if path.exists():
            raise ValueError(f"immutable_backup_exists:{path}")
        os.replace(temporary_path, path)
        fsync_directory(path.parent)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def parse_external_specs(values: list[str]) -> list[tuple[str, Path]]:
    parsed: list[tuple[str, Path]] = []
    labels: set[str] = set()
    for value in values:
        if "=" not in value:
            raise ValueError(f"external_requires_label_path:{value}")
        label, raw_path = value.split("=", 1)
        if not EXTERNAL_LABEL_RE.fullmatch(label) or label in labels:
            raise ValueError(f"invalid_or_duplicate_external_label:{label}")
        path = Path(raw_path).expanduser()
        if path.is_symlink():
            raise ValueError(f"external_symlink_not_supported:{path}")
        path = path.resolve()
        if not path.exists():
            raise ValueError(f"external_not_found:{path}")
        if path.is_symlink():
            raise ValueError(f"external_symlink_not_supported:{path}")
        labels.add(label)
        parsed.append((label, path))
    return parsed


def collect_entries(
    vault: Path,
    externals: list[tuple[str, Path]],
) -> tuple[list[tuple[Path, str]], dict[str, str], list[dict[str, object]]]:
    entries: list[tuple[Path, str]] = []
    files: dict[str, str] = {}
    vault_files = file_map(vault)
    for relative, digest in vault_files.items():
        archive_path = f"vault/{relative}"
        entries.append((vault / relative, archive_path))
        files[archive_path] = digest
    sources: list[dict[str, object]] = [
        {
            "id": "vault",
            "kind": "vault",
            "source": str(vault),
            "archive_prefix": "vault/",
            "file_count": len(vault_files),
        }
    ]
    for label, source in externals:
        before = len(files)
        if source.is_file():
            relative_files = [(source, source.name)]
            kind = "external-file"
        elif source.is_dir():
            for path in source.rglob("*"):
                if path.is_symlink():
                    raise ValueError(f"external_symlink_not_supported:{path}")
            relative_files = [
                (path, path.relative_to(source).as_posix())
                for path in sorted(source.rglob("*"))
                if path.is_file() and not path.is_symlink()
            ]
            kind = "external-directory"
        else:
            raise ValueError(f"external_source_not_file_or_directory:{source}")
        for path, relative in relative_files:
            archive_path = f"external/{label}/{relative}"
            entries.append((path, archive_path))
            files[archive_path] = sha256(path)
        sources.append(
            {
                "id": label,
                "kind": kind,
                "source": str(source),
                "archive_prefix": f"external/{label}/",
                "file_count": len(files) - before,
            }
        )
    return entries, files, sources


def snapshot(
    vault: Path,
    destination: Path,
    label: str,
    externals: list[tuple[str, Path]] | None = None,
) -> dict[str, object]:
    if vault.is_symlink():
        raise ValueError(f"vault_symlink_not_supported:{vault}")
    vault = vault.resolve()
    destination = destination.resolve()
    if not vault.is_dir():
        raise ValueError(f"vault_not_found:{vault}")
    if not EXTERNAL_LABEL_RE.fullmatch(label) or label in {".", ".."}:
        raise ValueError("invalid_backup_label")
    for source in [vault, *(path.resolve() for _, path in (externals or []) if path.is_dir())]:
        if destination == source or source in destination.parents:
            raise ValueError("backup_destination_inside_source")
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    base = destination / f"{vault.name}-{label}-{stamp}"
    archive = base.with_suffix(".tar.gz")
    manifest = base.with_suffix(".manifest.json")
    entries, files, sources = collect_entries(vault, externals or [])
    if archive.exists() or manifest.exists():
        raise ValueError(f"immutable_backup_exists:{base}")
    with tempfile.NamedTemporaryFile(dir=destination, prefix=archive.name + ".", delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        with tarfile.open(temp_path, "w:gz") as bundle:
            for source, archive_path in entries:
                bundle.add(source, arcname=archive_path, recursive=False)
        with temp_path.open("rb") as completed_archive:
            seal_read_only(completed_archive.fileno())
        temp_path.replace(archive)
        fsync_directory(destination)
    finally:
        temp_path.unlink(missing_ok=True)
    payload = {
        "schema": SCHEMA,
        "level": "snapshot-created",
        "restore_verified": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "vault": str(vault),
        "archive": str(archive),
        "archive_sha256": sha256(archive),
        "file_count": len(files),
        "vault_file_count": sum(1 for path in files if path.startswith("vault/")),
        "external_source_count": len(sources) - 1,
        "sources": sources,
        "files": files,
        "manifest": str(manifest),
    }
    atomic_write_json(manifest, payload)
    modes = backup_file_modes(archive, manifest)
    if any(mode != "0400" for mode in modes.values()):
        raise OSError(f"backup_mode_readback_failed:{modes}")
    return payload


def verify_restore(manifest_path: Path, workdir: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archive = Path(manifest["archive"])
    blockers: list[str] = []
    modes = backup_file_modes(archive, manifest_path)
    blockers.extend(f"{name}_missing" if mode is None else f"{name}_mode_not_0400" for name, mode in modes.items() if mode != "0400")
    if blockers:
        return {"schema": "vault-restore-verification/v1", "backup": str(manifest_path), "level": "blocked", "blockers": blockers, "mismatches": [], "file_modes": modes}
    if not archive.is_file() or sha256(archive) != manifest["archive_sha256"]:
        blockers.append("archive_sha256_mismatch")
        return {"schema": "vault-restore-verification/v1", "backup": str(manifest_path), "level": "blocked", "blockers": blockers, "mismatches": [], "file_modes": modes}
    workdir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=workdir, prefix="restore-") as temporary:
        restore_root = Path(temporary)
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(restore_root, filter="data")
        restored = file_map(restore_root) if manifest.get("schema") == "vault-backup/v1" else all_file_map(restore_root)
    expected = manifest["files"]
    mismatches = sorted({*expected, *restored} - {path for path in expected if expected.get(path) == restored.get(path)})
    return {"schema": "vault-restore-verification/v1", "backup": str(manifest_path), "level": "verified-working" if not mismatches else "blocked", "blockers": [] if not mismatches else ["restored_content_mismatch"], "mismatches": mismatches, "file_modes": modes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("snapshot")
    create.add_argument("--vault", required=True)
    create.add_argument("--destination", required=True)
    create.add_argument("--label", required=True)
    create.add_argument("--external", action="append", default=[], help="Approved external state as label=/absolute/path")
    verify = sub.add_parser("verify-restore")
    verify.add_argument("--backup", required=True)
    verify.add_argument("--workdir", required=True)
    for child in (create, verify):
        child.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "snapshot":
            payload = snapshot(
                Path(args.vault).expanduser(),
                Path(args.destination).expanduser(),
                args.label,
                parse_external_specs(args.external),
            )
        else:
            payload = verify_restore(Path(args.backup).expanduser().resolve(), Path(args.workdir).expanduser().resolve())
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["level"] != "blocked" else 1
    except (ValueError, OSError, tarfile.TarError, json.JSONDecodeError) as error:
        print(json.dumps({"schema": SCHEMA, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
