from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__


REQUIRED_STARTUP_FILES = ["_CLAUDE.md", "index.md", "Home.md", "CRITICAL_FACTS.md"]
VALID_RELATIONS = {
    "preferred_tool_for",
    "workflow_shortcut",
    "evidence_chain",
    "verified_by",
    "avoid_if",
    "suppress",
    "supersedes",
}
VALID_CAPTURE_TYPES = {
    "route-worked",
    "route-failed",
    "decision",
    "proof-chain",
    "mapping",
    "deliverable",
    "contradiction",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSONL: {exc}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{line_no}: expected JSON object")
        rows.append(item)
    return rows


def write_jsonl_append(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def markdown_stub(title: str, body: str) -> str:
    today = datetime.now().date().isoformat()
    return f"""---
date: {today}
type: system
tags:
  - second-brain
ai-first: true
---

# {title}

## For future Claude

{body}
"""


def command_init(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    vault.mkdir(parents=True, exist_ok=True)

    files = {
        "_CLAUDE.md": markdown_stub(
            "Agent Operating Manual",
            "Startup context, routing rules, delivery-first behavior, evidence boundaries, and safety rules for this vault.",
        ),
        "index.md": markdown_stub(
            "Index",
            "Navigation layer for future agents. Keep this small and update it when durable notes are added.",
        ),
        "Home.md": markdown_stub(
            "Home",
            "Human-facing dashboard for the vault. Link only the highest-value entry points here.",
        ),
        "CRITICAL_FACTS.md": markdown_stub(
            "CRITICAL_FACTS",
            "Tiny always-load facts. Keep this file short so startup context stays fast.",
        ),
    }

    created: list[str] = []
    skipped: list[str] = []
    for name, content in files.items():
        target = vault / name
        if target.exists() and not args.force:
            skipped.append(name)
            continue
        target.write_text(content, encoding="utf-8")
        created.append(name)

    graph = vault / "memory-graph.jsonl"
    captures = vault / "captures.jsonl"
    for target in [graph, captures]:
        if target.exists() and not args.force:
            skipped.append(target.name)
            continue
        target.write_text("", encoding="utf-8")
        created.append(target.name)

    print(json.dumps({"vault": str(vault), "created": created, "skipped": skipped}, indent=2))
    return 0


def validate_edge(edge: dict[str, Any], source: str) -> list[str]:
    errors: list[str] = []
    required = ["id", "from", "to", "relation", "weight", "confidence", "evidence", "action"]
    for key in required:
        if key not in edge:
            errors.append(f"{source}: missing edge field '{key}'")
    relation = edge.get("relation")
    if relation is not None and relation not in VALID_RELATIONS:
        errors.append(f"{source}: invalid relation '{relation}'")
    weight = edge.get("weight")
    if weight is not None and not isinstance(weight, (int, float)):
        errors.append(f"{source}: weight must be numeric")
    if isinstance(weight, (int, float)) and not 0 <= float(weight) <= 1:
        errors.append(f"{source}: weight must be between 0 and 1")
    evidence = edge.get("evidence")
    if evidence is not None and not isinstance(evidence, list):
        errors.append(f"{source}: evidence must be an array")
    return errors


def validate_capture(event: dict[str, Any], source: str) -> list[str]:
    errors: list[str] = []
    required = ["id", "timestamp", "type", "summary", "evidence"]
    for key in required:
        if key not in event:
            errors.append(f"{source}: missing capture field '{key}'")
    event_type = event.get("type")
    if event_type is not None and event_type not in VALID_CAPTURE_TYPES:
        errors.append(f"{source}: invalid capture type '{event_type}'")
    if "evidence" in event and not isinstance(event["evidence"], list):
        errors.append(f"{source}: evidence must be an array")
    return errors


def command_validate(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not vault.exists():
        errors.append(f"{vault}: vault path does not exist")
    else:
        for name in REQUIRED_STARTUP_FILES:
            target = vault / name
            if not target.exists():
                errors.append(f"missing startup file: {name}")
            elif "## For future Claude" not in target.read_text(encoding="utf-8", errors="ignore"):
                warnings.append(f"{name}: missing '## For future Claude' preamble")

        for path in [vault / "memory-graph.jsonl", vault / "fixtures" / "memory-graph.jsonl"]:
            try:
                for index, edge in enumerate(read_jsonl(path), 1):
                    errors.extend(validate_edge(edge, f"{path}:{index}"))
            except ValueError as exc:
                errors.append(str(exc))

        for path in [vault / "captures.jsonl", vault / "fixtures" / "capture-events.jsonl"]:
            try:
                for index, event in enumerate(read_jsonl(path), 1):
                    errors.extend(validate_capture(event, f"{path}:{index}"))
            except ValueError as exc:
                errors.append(str(exc))

    result = {
        "vault": str(vault),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


def make_capture_event(args: argparse.Namespace) -> dict[str, Any]:
    slug = re.sub(r"[^a-z0-9]+", "-", args.summary.lower()).strip("-")[:64] or "capture"
    return {
        "id": f"capture_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{slug}",
        "timestamp": utc_now(),
        "type": args.type,
        "summary": args.summary,
        "evidence": args.evidence or [],
        "route": args.route,
        "outcome": args.outcome,
        "dry_run_first": not args.write,
    }


def command_capture(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    event = make_capture_event(args)
    errors = validate_capture(event, "capture")
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2), file=sys.stderr)
        return 1
    if args.write:
        write_jsonl_append(vault / "captures.jsonl", event)
    print(json.dumps({"ok": True, "written": bool(args.write), "event": event}, indent=2))
    return 0


def collect_markdown_files(vault: Path) -> list[Path]:
    ignored_parts = {".git", ".obsidian", "_trash"}
    result = []
    for path in vault.rglob("*.md"):
        if ignored_parts.intersection(path.parts):
            continue
        result.append(path)
    return sorted(result)


def incoming_link_counts(vault: Path, markdown_files: list[Path]) -> dict[str, int]:
    names = {path.stem: 0 for path in markdown_files}
    pattern = re.compile(r"\[\[([^\]#|]+)")
    for path in markdown_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in pattern.findall(text):
            target = Path(match).stem
            if target in names:
                names[target] += 1
    return names


def command_consolidate(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    markdown_files = collect_markdown_files(vault) if vault.exists() else []
    link_counts = incoming_link_counts(vault, markdown_files) if vault.exists() else {}
    startup_missing = [name for name in REQUIRED_STARTUP_FILES if not (vault / name).exists()]
    orphan_candidates = [
        str(path.relative_to(vault))
        for path in markdown_files
        if link_counts.get(path.stem, 0) == 0 and path.name not in REQUIRED_STARTUP_FILES
    ][:25]
    low_confidence_edges: list[str] = []
    for graph_path in [vault / "memory-graph.jsonl", vault / "fixtures" / "memory-graph.jsonl"]:
        try:
            for edge in read_jsonl(graph_path):
                if float(edge.get("weight", 1)) < 0.5:
                    low_confidence_edges.append(edge.get("id", "unknown"))
        except (ValueError, TypeError):
            low_confidence_edges.append(f"invalid:{graph_path}")

    report = {
        "vault": str(vault),
        "mode": "dry-run" if args.dry_run or not args.write else "write",
        "would_change": [],
        "startup_missing": startup_missing,
        "markdown_file_count": len(markdown_files),
        "orphan_candidates": orphan_candidates,
        "low_confidence_edges": low_confidence_edges,
        "permission_required_for": [
            "deleting notes",
            "archiving evidence",
            "merging notes",
            "rewriting dense historical logs",
            "publishing private content",
        ],
    }
    if args.write:
        # The reference implementation deliberately reports only.
        report["would_change"].append("No automatic writes implemented in public reference CLI.")
    print(json.dumps(report, indent=2))
    return 0


def load_edges_for_route(vault: Path) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for path in [vault / "memory-graph.jsonl", vault / "fixtures" / "memory-graph.jsonl"]:
        try:
            edges.extend(read_jsonl(path))
        except ValueError:
            continue
    return edges


def score_edge(query: str, edge: dict[str, Any]) -> float:
    haystack = " ".join(
        str(edge.get(key, ""))
        for key in ["from", "to", "relation", "confidence", "action", "interruption_policy"]
    ).lower()
    query_tokens = {token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 2}
    if not query_tokens:
        return float(edge.get("weight", 0))
    matches = sum(1 for token in query_tokens if token in haystack)
    return matches + float(edge.get("weight", 0))


def command_route_suggest(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    edges = load_edges_for_route(vault)
    ranked = sorted(edges, key=lambda edge: score_edge(args.query, edge), reverse=True)
    suggestions = [
        {
            "id": edge.get("id"),
            "relation": edge.get("relation"),
            "weight": edge.get("weight"),
            "action": edge.get("action"),
            "evidence": edge.get("evidence", []),
            "interruption_policy": edge.get("interruption_policy"),
        }
        for edge in ranked[: args.limit]
        if score_edge(args.query, edge) > 0
    ]
    print(json.dumps({"query": args.query, "suggestions": suggestions}, indent=2))
    return 0 if suggestions else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="second-brain")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a minimal AI-first vault skeleton")
    init_parser.add_argument("vault", help="target vault directory")
    init_parser.add_argument("--force", action="store_true", help="overwrite generated files")
    init_parser.set_defaults(func=command_init)

    validate_parser = subparsers.add_parser("validate", help="validate startup files and JSONL fixtures")
    validate_parser.add_argument("vault", help="vault directory")
    validate_parser.set_defaults(func=command_validate)

    capture_parser = subparsers.add_parser("capture", help="create a capture event; dry-run unless --write is set")
    capture_parser.add_argument("--vault", default=".", help="vault directory")
    capture_parser.add_argument("--type", required=True, choices=sorted(VALID_CAPTURE_TYPES))
    capture_parser.add_argument("--summary", required=True)
    capture_parser.add_argument("--evidence", action="append", default=[])
    capture_parser.add_argument("--route")
    capture_parser.add_argument("--outcome")
    capture_parser.add_argument("--write", action="store_true", help="append event to captures.jsonl")
    capture_parser.set_defaults(func=command_capture)

    consolidate_parser = subparsers.add_parser("consolidate", help="produce a safe consolidation report")
    consolidate_parser.add_argument("vault", help="vault directory")
    consolidate_parser.add_argument("--dry-run", action="store_true", help="report only")
    consolidate_parser.add_argument("--write", action="store_true", help="reserved for future use; no destructive writes")
    consolidate_parser.set_defaults(func=command_consolidate)

    route_parser = subparsers.add_parser("route-suggest", help="suggest a route from memory graph edges")
    route_parser.add_argument("vault", help="vault directory")
    route_parser.add_argument("query", help="task description")
    route_parser.add_argument("--limit", type=int, default=3)
    route_parser.set_defaults(func=command_route_suggest)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
