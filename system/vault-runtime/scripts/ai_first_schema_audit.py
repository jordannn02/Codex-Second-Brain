#!/usr/bin/env python3
"""Audit AI-first metadata validity and naming drift without editing notes."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from vault_health import FRONTMATTER_RE, SCOPE_PROFILES, load_vault, scope_exclusions


SCHEMA = "ai-first-schema-audit/v1"
TOP_LEVEL_FIELD = re.compile(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$")


def parse_frontmatter(frontmatter: str) -> dict[str, object]:
    """Parse the top-level YAML subset used by universal AI-first fields."""
    fields: dict[str, object] = {}
    active_list: str | None = None
    for line in frontmatter.splitlines():
        match = TOP_LEVEL_FIELD.match(line)
        if match:
            key, raw = match.groups()
            raw = (raw or "").strip()
            active_list = key if not raw else None
            if not raw:
                fields[key] = []
            elif raw.startswith("[") and raw.endswith("]"):
                fields[key] = [item.strip().strip("\"'") for item in raw[1:-1].split(",") if item.strip()]
            else:
                fields[key] = raw.strip("\"'")
            continue
        stripped = line.strip()
        if active_list and stripped.startswith("-"):
            value = stripped[1:].strip().strip("\"'")
            if value:
                current = fields[active_list]
                assert isinstance(current, list)
                current.append(value)
    return fields


def issue(path: str, kind: str, severity: str, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {"path": path, "kind": kind, "severity": severity}
    row.update(extra)
    return row


def load_target_notes(vault: Path, targets: list[str]) -> tuple[dict[str, dict[str, object]], list[str]]:
    notes: dict[str, dict[str, object]] = {}
    normalized: list[str] = []
    for raw in targets:
        relative = Path(raw)
        if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".md":
            raise ValueError(f"invalid Markdown target: {raw}")
        path = (vault / relative).resolve()
        try:
            canonical_relative = path.relative_to(vault).as_posix()
        except ValueError as error:
            raise ValueError(f"target outside vault: {raw}") from error
        if not path.is_file():
            raise ValueError(f"target not found: {raw}")
        if canonical_relative in notes:
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        match = FRONTMATTER_RE.match(content)
        notes[canonical_relative] = {
            "path": path,
            "rel": canonical_relative,
            "content": content,
            "frontmatter": match.group(1) if match else "",
        }
        normalized.append(canonical_relative)
    return notes, normalized


def audit(
    vault: Path,
    policy: dict[str, Any],
    scope: str,
    targets: list[str] | None = None,
) -> dict[str, object]:
    profile = SCOPE_PROFILES[scope]
    if targets:
        notes, selected_targets = load_target_notes(vault, targets)
        selection = {"mode": "targets", "targets": selected_targets}
    else:
        notes = load_vault(vault, profile)
        selection = {"mode": "scope", "targets": []}
    exempt_paths = set(policy.get("exempt_paths", []))
    aliases = {str(key): str(value) for key, value in policy.get("type_aliases", {}).items()}
    canonical_heading = str(policy["canonical_preamble"])
    heading_aliases = {str(value) for value in policy.get("preamble_aliases", [])}
    required_fields = [str(value) for value in policy.get("required_fields", [])]

    raw_types: Counter[str] = Counter()
    canonical_types: Counter[str] = Counter()
    drift_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    issues: list[dict[str, object]] = []
    scanned = 0

    for relative in sorted(notes):
        if relative in exempt_paths:
            continue
        scanned += 1
        note = notes[relative]
        fields = parse_frontmatter(str(note["frontmatter"]))

        for field in required_fields:
            if field == "ai-first":
                if str(fields.get(field, "")).lower() != "true":
                    blocker_counts["ai_first_not_true"] += 1
                    issues.append(issue(relative, "ai_first_not_true", "blocker"))
            elif field not in fields or fields[field] in (None, "", []):
                kind = f"missing_{field.replace('-', '_')}"
                blocker_counts[kind] += 1
                issues.append(issue(relative, kind, "blocker"))

        raw_type = fields.get("type")
        if isinstance(raw_type, str) and raw_type:
            raw_types[raw_type] += 1
            canonical_type = aliases.get(raw_type, raw_type)
            canonical_types[canonical_type] += 1
            if canonical_type != raw_type:
                drift_counts["type_alias"] += 1
                issues.append(issue(relative, "type_alias", "drift", raw=raw_type, canonical=canonical_type))

        headings = {line.strip() for line in str(note["content"]).splitlines() if line.startswith("## ")}
        if canonical_heading in headings:
            pass
        else:
            matched_alias = sorted(headings & heading_aliases)
            if matched_alias:
                drift_counts["heading_alias"] += 1
                issues.append(issue(relative, "heading_alias", "drift", raw=matched_alias[0], canonical=canonical_heading))
            else:
                blocker_counts["missing_preamble"] += 1
                issues.append(issue(relative, "missing_preamble", "blocker"))

    blockers = sorted(f"{row['path']}:{row['kind']}" for row in issues if row["severity"] == "blocker")
    has_drift = bool(drift_counts)
    strict_targets = selection["mode"] == "targets"
    if strict_targets and blockers:
        level = "blocked"
    elif blockers or has_drift:
        level = "degraded"
    else:
        level = "verified-working"
    return {
        "schema": SCHEMA,
        "policy_schema": policy.get("schema"),
        "vault": str(vault),
        "scope": {"profile": profile.name, "description": profile.description, "include": list(profile.include)},
        "selection": selection,
        "exclusions": scope_exclusions(profile),
        "level": level,
        "enforcement_mode": "strict-targets" if strict_targets else "report-only-legacy",
        "validation_level": "blocked" if blockers else "verified-working",
        "stats": {
            "notes_scanned": scanned,
            "raw_types": dict(sorted(raw_types.items())),
            "canonical_types": dict(sorted(canonical_types.items())),
            "drift_counts": dict(sorted(drift_counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
        },
        "issues": issues,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=".")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--scope", default="core", choices=sorted(SCOPE_PROFILES))
    parser.add_argument("--target", action="append", default=[], help="Exact relative Markdown target to validate")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        vault = Path(args.path).expanduser().resolve()
        policy = json.loads(Path(args.policy).expanduser().read_text(encoding="utf-8"))
        payload = audit(vault, policy, args.scope, args.target or None)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["level"])
        return 1 if payload["level"] == "blocked" else 0
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"schema": SCHEMA, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
