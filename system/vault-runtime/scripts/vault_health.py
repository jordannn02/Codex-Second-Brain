#!/usr/bin/env python3
"""Read-only Obsidian vault health check.

This is a vault-local health runner. It is
safe by default: it scans Markdown files, reports findings, and never edits
notes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable


TODAY = date.today()

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
CODE_FENCE_WRAP_RE = re.compile(r"\A\s*```[^\n]*\n\s*---\s*\n")
WIKILINK_RE = re.compile(r"\[\[(.+?)\]\]")
DUE_RE = re.compile(r"due:\s*(\d{4}-\d{2}-\d{2})")
KANBAN_DATE_RE = re.compile(r"@\{(\d{4}-\d{2}-\d{2})\}")
KANBAN_TASK_RE = re.compile(
    r"^\s*[-*+]\s+\[\s\].*?@\{(\d{4}-\d{2}-\d{2})\}.*$",
    re.MULTILINE,
)
TEMPLATE_RE = re.compile(r"<%.*?%>", re.DOTALL)
ALIAS_RE = re.compile(r"^aliases:\s*\n((?:\s+-\s+.+\n?)+)", re.MULTILINE)
SOURCE_HASH_RE = re.compile(r"^source_hash:\s*[\"']?([^\"'\n]+)[\"']?\s*$", re.MULTILINE)
DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\s+[-\u2013\u2014]\s+|\s+)")

COMMON_DIR_EXCLUDES = {".git", ".obsidian", ".trash", "_trash", "Templates"}
DEFAULT_ROOT_FILE_EXCLUDES = {"AGENTS.md", "INSTALL.md"}
RECURRING_DATED_FOLDERS = {"Daily", "Dev Logs", "Logs", "Reviews"}


@dataclass(frozen=True)
class ScopeProfile:
    name: str
    description: str
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    root_file_excludes: tuple[str, ...] = tuple(sorted(DEFAULT_ROOT_FILE_EXCLUDES))


SCOPE_PROFILES: dict[str, ScopeProfile] = {
    "core": ScopeProfile(
        name="core",
        description="Vault operating notes and project notes, excluding tooling, imported knowledge, outputs, and public package fixtures.",
        include=("",),
        exclude=(
            ".codex/",
            "Knowledge/",
            "outputs/",
        ),
    ),
    "knowledge": ScopeProfile(
        name="knowledge",
        description="Knowledge notes only.",
        include=("Knowledge/",),
        exclude=(),
    ),
    "tooling": ScopeProfile(
        name="tooling",
        description="Vault tooling and command specifications.",
        include=(".codex/", "AGENTS.md", "_CLAUDE.md", "CRITICAL_FACTS.md", "Home.md", "index.md"),
        exclude=(),
        root_file_excludes=(),
    ),
    "public-package": ScopeProfile(
        name="public-package",
        description="Public package source, docs, tests, and demo vault fixtures.",
        include=("public-package/",),
        exclude=(),
        root_file_excludes=(),
    ),
    "all": ScopeProfile(
        name="all",
        description="Whole vault scan except common system folders.",
        include=("",),
        exclude=(),
        root_file_excludes=(),
    ),
}


def relpath(path: Path, vault: Path) -> str:
    return path.relative_to(vault).as_posix()


def runner_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def normalize_dashes(value: str) -> str:
    return value.replace("\u2014", "-").replace("\u2013", "-")


def normalize_link_target(target: str) -> str:
    target = target.strip().rstrip("\\")
    for sep in ("|", "#"):
        if sep in target:
            target = target.split(sep, 1)[0]
    return target.strip()


def extract_wikilinks(content: str) -> list[str]:
    return [normalize_link_target(match.group(1)) for match in WIKILINK_RE.finditer(content)]


def parse_aliases(frontmatter: str) -> list[str]:
    match = ALIAS_RE.search(frontmatter)
    if not match:
        return []
    aliases: list[str] = []
    for line in match.group(1).splitlines():
        alias = line.strip()
        if alias.startswith("-"):
            aliases.append(alias[1:].strip().strip("\"'"))
    return aliases


def parse_source_hash(frontmatter: str) -> str | None:
    match = SOURCE_HASH_RE.search(frontmatter)
    return match.group(1).strip() if match else None


def is_under(rel: str, prefix: str) -> bool:
    if not prefix:
        return True
    normalized = prefix.rstrip("/")
    return rel == normalized or rel.startswith(normalized + "/")


def matches_scope(rel: str, profile: ScopeProfile) -> bool:
    if Path(rel).name in profile.root_file_excludes and "/" not in rel:
        return False
    included = any(is_under(rel, prefix) for prefix in profile.include)
    excluded = any(is_under(rel, prefix) for prefix in profile.exclude)
    return included and not excluded


def scope_exclusions(profile: ScopeProfile) -> dict[str, object]:
    return {
        "common_dir_excludes": sorted(COMMON_DIR_EXCLUDES),
        "profile_excludes": list(profile.exclude),
        "root_file_excludes": list(profile.root_file_excludes),
    }


def iter_markdown(vault: Path, profile: ScopeProfile) -> Iterable[Path]:
    for md in vault.rglob("*.md"):
        rel = relpath(md, vault)
        if any(part in COMMON_DIR_EXCLUDES for part in md.relative_to(vault).parts):
            continue
        if matches_scope(rel, profile):
            yield md


def load_vault(vault: Path, profile: ScopeProfile) -> dict[str, dict[str, object]]:
    notes: dict[str, dict[str, object]] = {}
    for md in iter_markdown(vault, profile):
        rel = relpath(md, vault)
        content = md.read_text(encoding="utf-8", errors="replace")
        fm_match = FRONTMATTER_RE.match(content)
        frontmatter = fm_match.group(1) if fm_match else ""
        due_match = DUE_RE.search(frontmatter)
        due = due_match.group(1) if due_match else None
        notes[rel] = {
            "path": md,
            "rel": rel,
            "stem": md.stem,
            "content": content,
            "frontmatter": frontmatter,
            "has_frontmatter": bool(fm_match),
            "code_fence_wrapped": bool(not fm_match and CODE_FENCE_WRAP_RE.match(content)),
            "links": extract_wikilinks(content),
            "aliases": parse_aliases(frontmatter),
            "source_hash": parse_source_hash(frontmatter),
            "due": due,
            "size": len(content),
        }
    return notes


def issue(issue_type: str, severity: str, message: str, files: list[str], **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": issue_type,
        "severity": severity,
        "message": message,
        "files": files,
    }
    payload.update(extra)
    return payload


def is_recurring_dated_series(files: list[str]) -> bool:
    dates: list[str] = []
    for rel in files:
        if rel.split("/", 1)[0] not in RECURRING_DATED_FOLDERS:
            return False
        match = DATE_PREFIX_RE.match(Path(rel).stem)
        if not match:
            return False
        dates.append(match.group(1))
    return len(set(dates)) == len(files)


def check_duplicate_stems(notes: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    stems: dict[str, list[str]] = defaultdict(list)
    for rel, note in notes.items():
        norm = re.sub(r"\d{4}-\d{2}-\d{2}", "", str(note["stem"])).lower()
        norm = re.sub(r"[^a-z0-9 ]", " ", norm).strip()
        norm = re.sub(r"\s+", " ", norm)
        stems[norm].append(rel)
    return [
        issue("duplicate", "warning", f"Possible duplicates: {norm!r}", files)
        for norm, files in stems.items()
        if len(files) > 1 and norm and not is_recurring_dated_series(files)
    ]


def check_source_hash_duplicates(notes: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    hashes: dict[str, list[str]] = defaultdict(list)
    for rel, note in notes.items():
        source_hash = note.get("source_hash")
        if source_hash:
            hashes[str(source_hash)].append(rel)
    return [
        issue(
            "source_hash_duplicate",
            "warning",
            f"Duplicate source_hash {source_hash}",
            files,
            source_hash=source_hash,
        )
        for source_hash, files in hashes.items()
        if len(files) > 1
    ]


def check_orphans(notes: dict[str, dict[str, object]], resolver_notes: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    all_links: set[str] = set()
    for note in resolver_notes.values():
        for link in note["links"]:
            lowered = str(link).lower()
            all_links.add(lowered)
            all_links.add(lowered.replace(" ", "-"))

    skip_folders = {"Daily", "Dev Logs", "Boards", "Templates", "Life Chapters", "Faith", "Reviews", "Partner", "Family"}
    findings: list[dict[str, object]] = []
    for rel, note in notes.items():
        top_folder = rel.split("/", 1)[0] if "/" in rel else ""
        if top_folder in skip_folders or rel in {"Home.md", "_CLAUDE.md"}:
            continue
        stem_lower = str(note["stem"]).lower()
        stem_norm = stem_lower.replace("-", " ").replace("_", " ")
        aliases = [str(alias).lower() for alias in note["aliases"]]
        linked = (
            stem_lower in all_links
            or stem_norm in all_links
            or any(stem_lower in link for link in all_links)
            or any(alias in all_links for alias in aliases)
        )
        if not linked:
            findings.append(issue("orphan", "info", f"No incoming links: {rel}", [rel]))
    return findings


def has_unchecked_task(content: str) -> bool:
    return bool(re.search(r"^\s*-\s+\[\s\]", content, re.MULTILINE))


def check_stale_tasks(notes: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for rel, note in notes.items():
        content = str(note["content"])
        kanban_tasks = list(KANBAN_TASK_RE.finditer(content))
        if kanban_tasks:
            for match in kanban_tasks:
                due = match.group(1)
                try:
                    due_date = date.fromisoformat(due)
                except ValueError:
                    continue
                if due_date >= TODAY:
                    continue
                line = content.count("\n", 0, match.start()) + 1
                days_overdue = (TODAY - due_date).days
                findings.append(
                    issue(
                        "stale_task",
                        "warning" if days_overdue > 7 else "info",
                        f"Overdue by {days_overdue}d: {rel}:{line}",
                        [rel],
                        due=due,
                        line=line,
                    )
                )
            continue

        due = note.get("due")
        if due and has_unchecked_task(content):
            try:
                due_date = date.fromisoformat(str(due))
            except ValueError:
                continue
            if due_date < TODAY:
                days_overdue = (TODAY - due_date).days
                findings.append(
                    issue(
                        "stale_task",
                        "warning" if days_overdue > 7 else "info",
                        f"Overdue by {days_overdue}d: {rel}",
                        [rel],
                        due=str(due),
                    )
                )
    return findings


def check_missing_frontmatter(notes: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for rel, note in notes.items():
        parts = set(rel.split("/"))
        if {"Templates", "_trash", ".obsidian"} & parts or rel in {"Home.md", "_CLAUDE.md"}:
            continue
        if note.get("code_fence_wrapped"):
            continue
        if not note["has_frontmatter"] and int(note["size"]) > 0:
            findings.append(issue("no_frontmatter", "warning", f"Missing frontmatter: {rel}", [rel]))
    return findings


def check_empty_markdown(notes: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    return [
        issue("empty_markdown", "warning", f"0-byte Markdown file: {rel}", [rel])
        for rel, note in notes.items()
        if int(note["size"]) == 0
    ]


def check_code_fence_wrapped(notes: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    return [
        issue("code_fence_wrapped", "error", f"Frontmatter trapped in fence - unwrap, don't add: {rel}", [rel])
        for rel, note in notes.items()
        if note.get("code_fence_wrapped")
    ]


def check_empty_folders(vault: Path, profile: ScopeProfile) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for folder in vault.rglob("*/"):
        if any(part in COMMON_DIR_EXCLUDES for part in folder.relative_to(vault).parts):
            continue
        if folder.is_dir() and not list(folder.iterdir()):
            rel = relpath(folder, vault)
            if matches_scope(rel, profile):
                findings.append(issue("empty_folder", "info", f"Empty folder: {rel}/", []))
    return findings


def check_broken_links(
    notes: dict[str, dict[str, object]],
    resolver_notes: dict[str, dict[str, object]],
    vault: Path,
) -> list[dict[str, object]]:
    all_stems = {str(note["stem"]).lower(): rel for rel, note in resolver_notes.items()}
    all_stems_dash_norm = {normalize_dashes(str(note["stem"])).lower(): rel for rel, note in resolver_notes.items()}
    all_aliases: dict[str, str] = {}
    for rel, note in resolver_notes.items():
        for alias in note["aliases"]:
            all_aliases[str(alias).lower()] = rel

    findings: list[dict[str, object]] = []
    for rel, note in notes.items():
        for link in note["links"]:
            link_text = str(link)
            link_stem = Path(link_text).stem.lower() if "/" in link_text else link_text.lower()
            link_norm = link_stem.replace("-", " ").replace("_", " ")
            link_dash_norm = normalize_dashes(link_stem)
            resolved = (
                link_stem in all_stems
                or link_norm in all_stems
                or link_stem in all_aliases
                or link_norm in all_aliases
                or link_dash_norm in all_stems_dash_norm
            )
            if not resolved and not (vault / link_text).is_dir():
                findings.append(issue("broken_link", "warning", f"Broken link [[{link_text}]] in {rel}", [rel]))
    return findings


def check_template_leftovers(notes: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for rel, note in notes.items():
        if any(part.lower() == "templates" for part in rel.split("/")):
            continue
        if TEMPLATE_RE.search(str(note["content"])):
            findings.append(issue("template_leftover", "error", f"Unfilled template syntax in: {rel}", [rel]))
    return findings


def run_health_check(vault: Path, profile: ScopeProfile) -> dict[str, object]:
    print(f"Scanning vault: {vault}", file=sys.stderr)
    print(f"Scope profile: {profile.name}", file=sys.stderr)
    notes = load_vault(vault, profile)
    resolver_notes = notes if profile.name == "all" else load_vault(vault, SCOPE_PROFILES["all"])
    print(f"Found {len(notes)} notes", file=sys.stderr)

    checks: list[tuple[str, Callable[[], list[dict[str, object]]]]] = [
        ("Duplicates", lambda: check_duplicate_stems(notes)),
        ("Source hash duplicates", lambda: check_source_hash_duplicates(notes)),
        ("Orphans", lambda: check_orphans(notes, resolver_notes)),
        ("Stale tasks", lambda: check_stale_tasks(notes)),
        ("Empty Markdown", lambda: check_empty_markdown(notes)),
        ("Code-fence-wrapped notes", lambda: check_code_fence_wrapped(notes)),
        ("Missing frontmatter", lambda: check_missing_frontmatter(notes)),
        ("Empty folders", lambda: check_empty_folders(vault, profile)),
        ("Broken links", lambda: check_broken_links(notes, resolver_notes, vault)),
        ("Template leftovers", lambda: check_template_leftovers(notes)),
    ]

    all_issues: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    for label, check in checks:
        findings = check()
        counts[label] = len(findings)
        all_issues.extend(findings)

    return {
        "vault": str(vault),
        "runner": "vault-local:.codex/scripts/vault_health.py",
        "runner_sha256": runner_sha256(),
        "scanned": TODAY.isoformat(),
        "scope": {
            "profile": profile.name,
            "description": profile.description,
            "include": list(profile.include),
        },
        "exclusions": scope_exclusions(profile),
        "total_notes": len(notes),
        "total_issues": len(all_issues),
        "counts": counts,
        "issues": all_issues,
    }


def print_report(result: dict[str, object]) -> None:
    scope = result["scope"]
    assert isinstance(scope, dict)
    print("=" * 60)
    print(f"VAULT HEALTH REPORT - {result['scanned']}")
    print(f"Runner: {result['runner']}")
    print(f"Runner SHA256: {result['runner_sha256']}")
    print(f"Scope: {scope['profile']}")
    print("=" * 60)
    print(f"Total notes: {result['total_notes']}")
    print(f"Total issues: {result['total_issues']}")
    print()
    counts = result["counts"]
    assert isinstance(counts, dict)
    for label, count in counts.items():
        print(f"- {label}: {count}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Obsidian vault health check")
    parser.add_argument("--path", default=".", help="Path to vault")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument(
        "--scope",
        default="core",
        choices=sorted(SCOPE_PROFILES),
        help="Scope profile to scan",
    )
    parser.add_argument("--list-scopes", action="store_true", help="List available scope profiles")
    parser.add_argument("--print-sha", action="store_true", help="Print this runner's SHA256 and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.print_sha:
        print(runner_sha256())
        return 0

    if args.list_scopes:
        payload = {
            name: {
                "description": profile.description,
                "include": list(profile.include),
                "exclusions": scope_exclusions(profile),
            }
            for name, profile in sorted(SCOPE_PROFILES.items())
        }
        print(json.dumps(payload, indent=2))
        return 0

    vault = Path(args.path).expanduser().resolve()
    if not vault.exists():
        print(f"Vault not found: {vault}", file=sys.stderr)
        return 1

    result = run_health_check(vault, SCOPE_PROFILES[args.scope])
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
