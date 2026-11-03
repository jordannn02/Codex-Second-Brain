#!/usr/bin/env python3
"""Audit empty scaffolds and duplicate evidence without modifying or deleting notes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from ai_first_schema_audit import parse_frontmatter
from vault_health import (
    COMMON_DIR_EXCLUDES,
    FRONTMATTER_RE,
    SCOPE_PROFILES,
    load_vault,
    matches_scope,
    scope_exclusions,
)


SCHEMA = "content-hygiene-audit/v1"
PLACEHOLDERS = {"tbd", "todo", "n/a", "na", "...", "-"}
INTENTIONAL_EMPTY_TYPES = {"imported-source-empty"}


def body_of(content: str) -> str:
    return FRONTMATTER_RE.sub("", content, count=1).strip()


def meaningful_text(body: str) -> str:
    lines: list[str] = []
    in_comment = False
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("<!--"):
            in_comment = True
        if in_comment:
            if line.endswith("-->"):
                in_comment = False
            continue
        if not line or line.startswith("#") or line.lower() in PLACEHOLDERS:
            continue
        lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def normalize_duplicate_target(value: object) -> str:
    target = str(value or "").strip()
    if target.startswith("[[") and target.endswith("]]"):
        target = target[2:-2]
    target = target.split("|", 1)[0].strip()
    if target and not target.endswith(".md"):
        target += ".md"
    return target


def acknowledged_source_group(
    files: list[str], fields_by_path: dict[str, dict[str, object]]
) -> dict[str, object] | None:
    references: dict[str, str] = {}
    for path in files:
        fields = fields_by_path.get(path, {})
        target = normalize_duplicate_target(fields.get("duplicate-of"))
        disposition = str(fields.get("duplicate-disposition", ""))
        if target and disposition == "reference-only":
            references[path] = target
    canonical_targets = set(references.values())
    if len(canonical_targets) != 1:
        return None
    canonical = canonical_targets.pop()
    if canonical not in files or set(references) != set(files) - {canonical}:
        return None
    return {"canonical": canonical, "references": sorted(references)}


def find_empty_directory_scaffolds(vault: Path, scope: str) -> list[str]:
    profile = SCOPE_PROFILES[scope]
    scaffolds: list[str] = []
    for folder in vault.rglob("*"):
        if not folder.is_dir():
            continue
        relative = folder.relative_to(vault)
        if any(part in COMMON_DIR_EXCLUDES for part in relative.parts):
            continue
        relative_path = relative.as_posix()
        if matches_scope(relative_path, profile) and not any(folder.iterdir()):
            scaffolds.append(relative_path + "/")
    return sorted(scaffolds)


def audit(vault: Path, scope: str) -> dict[str, object]:
    profile = SCOPE_PROFILES[scope]
    notes = load_vault(vault, profile)
    scaffolds: list[str] = []
    intentional_empty: list[str] = []
    content_hashes: dict[str, list[str]] = defaultdict(list)
    source_hashes: dict[str, list[str]] = defaultdict(list)
    fields_by_path: dict[str, dict[str, object]] = {}

    for relative in sorted(notes):
        note = notes[relative]
        fields = parse_frontmatter(str(note["frontmatter"]))
        fields_by_path[relative] = fields
        note_type = str(fields.get("type", ""))
        if note_type in INTENTIONAL_EMPTY_TYPES:
            intentional_empty.append(relative)
            continue
        content = body_of(str(note["content"]))
        meaningful = meaningful_text(content)
        if len(meaningful) < 20:
            scaffolds.append(relative)
            continue
        digest = hashlib.sha256(re.sub(r"\s+", " ", content).strip().encode("utf-8")).hexdigest()
        content_hashes[digest].append(relative)
        source_hash = note.get("source_hash")
        if source_hash:
            source_hashes[str(source_hash)].append(relative)

    duplicate_content = [
        {"content_sha256": digest, "files": files}
        for digest, files in sorted(content_hashes.items())
        if len(files) > 1
    ]
    duplicate_sources = [
        {"source_hash": source_hash, "files": files}
        for source_hash, files in sorted(source_hashes.items())
        if len(files) > 1
    ]
    acknowledged_duplicate_sources: list[dict[str, object]] = []
    unresolved_duplicate_sources: list[dict[str, object]] = []
    for group in duplicate_sources:
        files = group["files"]
        assert isinstance(files, list)
        acknowledgement = acknowledged_source_group(files, fields_by_path)
        if acknowledgement:
            acknowledged_duplicate_sources.append({**group, **acknowledgement})
        else:
            unresolved_duplicate_sources.append(group)
    empty_directories = find_empty_directory_scaffolds(vault, scope)
    blockers = [f"{path}:empty_scaffold" for path in scaffolds]
    has_review = bool(duplicate_content or unresolved_duplicate_sources or empty_directories)
    level = "blocked" if blockers else "degraded" if has_review else "verified-working"
    return {
        "schema": SCHEMA,
        "vault": str(vault),
        "scope": {"profile": profile.name, "description": profile.description, "include": list(profile.include)},
        "exclusions": scope_exclusions(profile),
        "level": level,
        "stats": {
            "notes_scanned": len(notes),
            "intentional_empty_sources": len(intentional_empty),
            "scaffold_notes": len(scaffolds),
            "empty_directory_scaffolds": len(empty_directories),
            "duplicate_content_groups": len(duplicate_content),
            "duplicate_source_hash_groups": len(duplicate_sources),
            "acknowledged_duplicate_source_hash_groups": len(acknowledged_duplicate_sources),
            "unresolved_duplicate_source_hash_groups": len(unresolved_duplicate_sources),
        },
        "intentional_empty_sources": intentional_empty,
        "scaffold_notes": scaffolds,
        "empty_directory_scaffolds": empty_directories,
        "duplicate_content_groups": duplicate_content,
        "duplicate_source_hash_groups": duplicate_sources,
        "acknowledged_duplicate_source_hash_groups": acknowledged_duplicate_sources,
        "unresolved_duplicate_source_hash_groups": unresolved_duplicate_sources,
        "repair_policy": {
            "mode": "review-only",
            "delete_authorized": False,
            "rule": "Report note, directory, and duplicate candidates only; never delete, merge, archive, or rewrite evidence-bearing notes automatically.",
        },
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=".")
    parser.add_argument("--scope", default="core", choices=sorted(SCOPE_PROFILES))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        payload = audit(Path(args.path).expanduser().resolve(), args.scope)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["level"])
        return 1 if payload["blockers"] else 0
    except (OSError, ValueError) as error:
        print(json.dumps({"schema": SCHEMA, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
