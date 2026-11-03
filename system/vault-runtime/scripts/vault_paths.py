#!/usr/bin/env python3
"""Resolve vault directory roles without assuming a wiki-style layout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROLE_CANDIDATES = {
    "daily": ("Daily", "wiki/daily"),
    "people": ("People", "wiki/entities"),
    "projects": ("Projects", "wiki/projects"),
    "tasks": ("Tasks", "wiki/tasks"),
    "concepts": ("Knowledge", "wiki/concepts"),
    "decisions": ("Knowledge/Decisions", "Knowledge", "wiki/decisions"),
    "boards": ("Boards", "boards"),
    "templates": ("Templates", "templates"),
}
LEGACY_PREFIXES = {
    "wiki/daily": "daily",
    "wiki/entities": "people",
    "wiki/projects": "projects",
    "wiki/tasks": "tasks",
    "wiki/concepts": "concepts",
    "wiki/decisions": "decisions",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, help="Vault root")
    parser.add_argument("--role", action="append", choices=sorted(ROLE_CANDIDATES))
    parser.add_argument("--validate", action="append", default=[], help="Relative path to validate")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def resolve_role(vault: Path, role: str) -> str:
    for candidate in ROLE_CANDIDATES[role]:
        if (vault / candidate).is_dir():
            return candidate
    return ROLE_CANDIDATES[role][0]


def resolve_legacy_path(vault: Path, raw_path: str) -> tuple[dict[str, object], bool]:
    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts:
        return {"input": raw_path, "resolved": None, "parent_exists": False}, False
    normalized = path.as_posix()
    for prefix, role in LEGACY_PREFIXES.items():
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            suffix = normalized.removeprefix(prefix).lstrip("/")
            resolved = Path(resolve_role(vault, role)) / suffix
            return {
                "input": raw_path,
                "resolved": resolved.as_posix(),
                "parent_exists": (vault / resolved).parent.is_dir(),
            }, True
    return {
        "input": raw_path,
        "resolved": normalized,
        "parent_exists": (vault / path).parent.is_dir(),
    }, (vault / path).parent.is_dir()


def main() -> int:
    args = parse_args()
    vault = Path(args.path).expanduser().resolve()
    if not vault.is_dir():
        raise SystemExit(f"Vault directory not found: {vault}")

    roles = args.role or sorted(ROLE_CANDIDATES)
    paths: list[dict[str, object]] = []
    valid = True
    for raw_path in args.validate:
        result, result_valid = resolve_legacy_path(vault, raw_path)
        paths.append(result)
        valid = valid and result_valid and bool(result["parent_exists"])

    result = {
        "vault": str(vault),
        "roles": {role: resolve_role(vault, role) for role in sorted(roles)},
        "valid": valid,
        "paths": paths,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for role, path in result["roles"].items():
            print(f"{role}={path}")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
