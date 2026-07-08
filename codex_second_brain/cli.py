from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
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
VALID_CONFIDENCE = {
    "unverified",
    "inferred",
    "verified-by-use",
    "verified-by-test",
    "stale",
    "suppressed",
}
VALID_DECAY_STATES = {"hot", "warm", "cold", "stale", "suppress"}
VALID_CAPTURE_TYPES = {
    "route-worked",
    "route-failed",
    "decision",
    "proof-chain",
    "mapping",
    "deliverable",
    "contradiction",
}
VALID_PRIVACY = {"public-safe", "private", "sensitive", "unknown"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


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


def write_jsonl_replace(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in items)
    path.write_text(text, encoding="utf-8")


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


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
            "Navigation layer for future agents. Keep it small and update it when durable notes are added.",
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

    for target in [vault / "memory-graph.jsonl", vault / "captures.jsonl"]:
        if target.exists() and not args.force:
            skipped.append(target.name)
            continue
        target.write_text("", encoding="utf-8")
        created.append(target.name)

    print_json({"vault": str(vault), "created": created, "skipped": skipped})
    return 0


def schemas_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas"


def schema_file(name: str) -> Path:
    return schemas_dir() / name


def fallback_validate_memory_edge(edge: dict[str, Any], source: str) -> list[str]:
    errors: list[str] = []
    required = [
        "id",
        "from",
        "to",
        "relation",
        "weight",
        "confidence",
        "decay_state",
        "success_count",
        "fail_count",
        "evidence",
        "action",
    ]
    allowed = set(required) | {"last_used", "failure_signature", "interruption_policy"}
    for key in required:
        if key not in edge:
            errors.append(f"schema {source}: missing required property '{key}'")
    for key in edge:
        if key not in allowed:
            errors.append(f"schema {source}: additional property '{key}' is not allowed")
    if "id" in edge and not re.match(r"^[a-z0-9][a-z0-9_\-]{2,120}$", str(edge["id"])):
        errors.append(f"schema {source}: id does not match required pattern")
    for key in ["from", "to", "action"]:
        if key in edge and (not isinstance(edge[key], str) or len(edge[key]) < 3):
            errors.append(f"schema {source}: {key} must be a string with length >= 3")
    if edge.get("relation") not in VALID_RELATIONS:
        errors.append(f"schema {source}: relation is not one of the allowed values")
    weight = edge.get("weight")
    if not isinstance(weight, (int, float)) or not 0 <= float(weight) <= 1:
        errors.append(f"schema {source}: weight must be a number between 0 and 1")
    if edge.get("confidence") not in VALID_CONFIDENCE:
        errors.append(f"schema {source}: confidence is not one of the allowed values")
    if edge.get("decay_state") not in VALID_DECAY_STATES:
        errors.append(f"schema {source}: decay_state is not one of the allowed values")
    for key in ["success_count", "fail_count"]:
        if not isinstance(edge.get(key), int) or edge.get(key, -1) < 0:
            errors.append(f"schema {source}: {key} must be a non-negative integer")
    evidence = edge.get("evidence")
    if not isinstance(evidence, list) or not all(isinstance(item, str) and item for item in evidence):
        errors.append(f"schema {source}: evidence must be an array of non-empty strings")
    if "last_used" in edge:
        try:
            parse_datetime(str(edge["last_used"]))
        except ValueError:
            errors.append(f"schema {source}: last_used must be a date-time")
    return errors


def fallback_validate_capture(event: dict[str, Any], source: str) -> list[str]:
    errors: list[str] = []
    required = ["id", "timestamp", "type", "summary", "evidence"]
    allowed = set(required) | {"route", "outcome", "privacy", "dry_run_first"}
    for key in required:
        if key not in event:
            errors.append(f"schema {source}: missing required property '{key}'")
    for key in event:
        if key not in allowed:
            errors.append(f"schema {source}: additional property '{key}' is not allowed")
    if "id" in event and not re.match(r"^[a-z0-9][a-z0-9_\-]{2,160}$", str(event["id"])):
        errors.append(f"schema {source}: id does not match required pattern")
    if event.get("type") not in VALID_CAPTURE_TYPES:
        errors.append(f"schema {source}: type is not one of the allowed values")
    if "summary" in event and (not isinstance(event["summary"], str) or len(event["summary"]) < 3):
        errors.append(f"schema {source}: summary must be a string with length >= 3")
    evidence = event.get("evidence")
    if not isinstance(evidence, list) or not all(isinstance(item, str) and item for item in evidence):
        errors.append(f"schema {source}: evidence must be an array of non-empty strings")
    if event.get("privacy", "unknown") not in VALID_PRIVACY:
        errors.append(f"schema {source}: privacy is not one of the allowed values")
    if "dry_run_first" in event and not isinstance(event["dry_run_first"], bool):
        errors.append(f"schema {source}: dry_run_first must be a boolean")
    if "timestamp" in event:
        try:
            parse_datetime(str(event["timestamp"]))
        except ValueError:
            errors.append(f"schema {source}: timestamp must be a date-time")
    return errors


def validate_against_json_schema(
    item: dict[str, Any],
    schema_name: str,
    source: str,
) -> tuple[list[str], str]:
    schema_path = schema_file(schema_name)
    if schema_path.exists():
        try:
            from jsonschema import Draft202012Validator, FormatChecker
        except ImportError:
            pass
        else:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            errors = [
                f"schema {source}: {error.message}"
                for error in sorted(validator.iter_errors(item), key=lambda err: list(err.path))
            ]
            return errors, "jsonschema"

    if schema_name == "memory-edge.schema.json":
        return fallback_validate_memory_edge(item, source), "builtin-fallback"
    if schema_name == "capture-event.schema.json":
        return fallback_validate_capture(item, source), "builtin-fallback"
    return [], "builtin-fallback"


def command_validate(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    schema_engines: set[str] = set()

    if not vault.exists():
        errors.append(f"vault does not exist: {vault}")
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
                    row_errors, engine = validate_against_json_schema(
                        edge,
                        "memory-edge.schema.json",
                        f"{path}:{index}",
                    )
                    schema_engines.add(engine)
                    errors.extend(row_errors)
            except ValueError as exc:
                errors.append(str(exc))

        for path in [vault / "captures.jsonl", vault / "fixtures" / "capture-events.jsonl"]:
            try:
                for index, event in enumerate(read_jsonl(path), 1):
                    row_errors, engine = validate_against_json_schema(
                        event,
                        "capture-event.schema.json",
                        f"{path}:{index}",
                    )
                    schema_engines.add(engine)
                    errors.extend(row_errors)
            except ValueError as exc:
                errors.append(str(exc))

    result = {
        "vault": str(vault),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "schema_engine": sorted(schema_engines) or ["not-run"],
    }
    print_json(result)
    return 0 if not errors else 1


def slugify(text: str, fallback: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:64] or fallback


def compact_utc_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz").lower()


def make_capture_event(args: argparse.Namespace) -> dict[str, Any]:
    slug = slugify(args.summary, "capture")
    event = {
        "id": f"capture_{compact_utc_id()}_{slug}",
        "timestamp": utc_now(),
        "type": args.type,
        "summary": args.summary,
        "evidence": args.evidence or [],
        "privacy": args.privacy,
        "dry_run_first": not args.write,
    }
    if args.route:
        event["route"] = args.route
    if args.outcome:
        event["outcome"] = args.outcome
    return event


def command_capture(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    event = make_capture_event(args)
    errors, _engine = validate_against_json_schema(event, "capture-event.schema.json", "capture")
    if errors:
        print_json({"ok": False, "errors": errors})
        return 1
    if args.write:
        write_jsonl_append(vault / "captures.jsonl", event)
    print_json({"ok": True, "written": bool(args.write), "event": event})
    return 0


def collect_markdown_files(vault: Path) -> list[Path]:
    ignored_parts = {".git", ".obsidian", "_trash"}
    result: list[Path] = []
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


def proposed_change(
    change_type: str,
    target: str,
    reason: str,
    requires_permission: bool,
    safe_to_apply: bool,
) -> dict[str, Any]:
    return {
        "type": change_type,
        "target": target,
        "reason": reason,
        "requires_permission": requires_permission,
        "safe_to_apply": safe_to_apply,
    }


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
    invalid_graphs: list[str] = []
    for graph_path in [vault / "memory-graph.jsonl", vault / "fixtures" / "memory-graph.jsonl"]:
        try:
            for index, edge in enumerate(read_jsonl(graph_path), 1):
                schema_errors, _engine = validate_against_json_schema(
                    edge,
                    "memory-edge.schema.json",
                    f"{graph_path}:{index}",
                )
                if schema_errors:
                    invalid_graphs.append(f"{graph_path}:{index}")
                elif float(edge.get("weight", 1)) < 0.5:
                    low_confidence_edges.append(edge.get("id", "unknown"))
        except (ValueError, TypeError):
            invalid_graphs.append(str(graph_path))

    changes: list[dict[str, Any]] = []
    for name in startup_missing:
        changes.append(
            proposed_change(
                "create_startup_file",
                name,
                "Required startup context file is missing.",
                requires_permission=False,
                safe_to_apply=True,
            )
        )
    for path in orphan_candidates[:10]:
        changes.append(
            proposed_change(
                "review_orphan_candidate",
                path,
                "Markdown note has no incoming wikilinks and may need routing, linking, or archival review.",
                requires_permission=False,
                safe_to_apply=False,
            )
        )
    for edge_id in low_confidence_edges[:10]:
        changes.append(
            proposed_change(
                "review_low_confidence_edge",
                edge_id,
                "Memory edge is weak and should be reinforced with evidence or allowed to decay.",
                requires_permission=False,
                safe_to_apply=False,
            )
        )
    for target in invalid_graphs[:10]:
        changes.append(
            proposed_change(
                "repair_invalid_graph",
                target,
                "Memory graph row does not match the public schema.",
                requires_permission=True,
                safe_to_apply=False,
            )
        )

    report = {
        "vault": str(vault),
        "mode": "dry-run" if args.dry_run or not args.write else "write",
        "would_change": [],
        "proposed_changes": changes,
        "startup_missing": startup_missing,
        "markdown_file_count": len(markdown_files),
        "orphan_candidates": orphan_candidates,
        "low_confidence_edges": low_confidence_edges,
        "invalid_graphs": invalid_graphs,
        "permission_required_for": [
            "deleting notes",
            "archiving evidence",
            "merging notes",
            "rewriting dense historical logs",
            "publishing private content",
        ],
    }
    if args.write:
        report["would_change"].append("No automatic destructive writes implemented in public reference CLI.")
    print_json(report)
    return 0


def load_edges_for_route(vault: Path) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for path in [vault / "fixtures" / "memory-graph.jsonl", vault / "memory-graph.jsonl"]:
        try:
            edges = read_jsonl(path)
        except ValueError:
            continue
        for edge in edges:
            edge_id = str(edge.get("id", ""))
            if not edge_id:
                continue
            if edge_id not in merged:
                order.append(edge_id)
            merged[edge_id] = edge
    return [merged[edge_id] for edge_id in order]


def write_memory_graph(vault: Path, edges: list[dict[str, Any]]) -> None:
    write_jsonl_replace(vault / "memory-graph.jsonl", edges)


def find_edge(edges: list[dict[str, Any]], edge_id: str) -> dict[str, Any] | None:
    for edge in edges:
        if edge.get("id") == edge_id:
            return edge
    return None


def append_unique(values: list[str], new_values: list[str]) -> list[str]:
    result = list(values)
    for value in new_values:
        if value and value not in result:
            result.append(value)
    return result


def decay_state_for_weight(weight: float) -> str:
    if weight >= 0.8:
        return "hot"
    if weight >= 0.65:
        return "warm"
    if weight >= 0.45:
        return "cold"
    if weight >= 0.25:
        return "stale"
    return "suppress"


def base_edge(
    edge_id: str,
    from_text: str,
    to_text: str,
    relation: str,
    action: str,
    evidence: list[str],
    weight: float = 0.6,
) -> dict[str, Any]:
    state = decay_state_for_weight(weight)
    return {
        "id": edge_id,
        "from": from_text,
        "to": to_text,
        "relation": relation,
        "weight": round(weight, 3),
        "confidence": "inferred",
        "decay_state": state,
        "success_count": 0,
        "fail_count": 0,
        "last_used": utc_now(),
        "evidence": evidence,
        "action": action,
        "interruption_policy": "Treat route memory as guidance; verify evidence before external writes.",
    }


def require_edge_inputs(args: argparse.Namespace) -> list[str]:
    missing: list[str] = []
    for attr, label in [("from_text", "--from"), ("to_text", "--to"), ("action", "--action")]:
        if not getattr(args, attr, None):
            missing.append(label)
    return missing


def apply_outcome(
    edge: dict[str, Any],
    outcome: str,
    evidence: list[str],
    failure_signature: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    updated = deepcopy(edge)
    updated["evidence"] = append_unique(list(updated.get("evidence", [])), evidence)
    updated["last_used"] = now or utc_now()
    updated.setdefault("success_count", 0)
    updated.setdefault("fail_count", 0)

    weight = float(updated.get("weight", 0.5))
    if outcome == "success":
        weight = min(1.0, weight + 0.05)
        updated["success_count"] = int(updated.get("success_count", 0)) + 1
        updated["confidence"] = "verified-by-use"
        updated["decay_state"] = decay_state_for_weight(weight)
        if updated.get("relation") == "suppress":
            updated["relation"] = "preferred_tool_for"
    elif outcome == "failure":
        weight = max(0.0, weight - 0.15)
        updated["fail_count"] = int(updated.get("fail_count", 0)) + 1
        updated["confidence"] = "suppressed" if weight < 0.25 else "stale"
        updated["decay_state"] = decay_state_for_weight(weight)
        if weight < 0.25:
            updated["relation"] = "suppress"
        if failure_signature:
            updated["failure_signature"] = failure_signature
    else:
        raise ValueError("outcome must be success or failure")

    updated["weight"] = round(weight, 3)
    return updated


def suppress_edge(
    edge: dict[str, Any],
    evidence: list[str],
    failure_signature: str | None,
) -> dict[str, Any]:
    updated = apply_outcome(edge, "failure", evidence, failure_signature)
    updated["weight"] = round(max(0.0, float(updated["weight"]) - 0.2), 3)
    updated["relation"] = "suppress"
    updated["confidence"] = "suppressed"
    updated["decay_state"] = "suppress"
    return updated


def validate_memory_edge_or_error(edge: dict[str, Any]) -> list[str]:
    errors, _engine = validate_against_json_schema(edge, "memory-edge.schema.json", f"edge:{edge.get('id', 'unknown')}")
    return errors


def command_record_outcome(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    edges = load_edges_for_route(vault)
    edge = find_edge(edges, args.edge_id)
    if edge is None:
        missing = require_edge_inputs(args)
        if missing:
            print_json({"ok": False, "errors": [f"new edge requires {', '.join(missing)}"]})
            return 2
        edge = base_edge(args.edge_id, args.from_text, args.to_text, args.relation, args.action, args.evidence)
        edges.append(edge)

    updated = apply_outcome(edge, args.outcome, args.evidence, args.failure_signature)
    errors = validate_memory_edge_or_error(updated)
    if errors:
        print_json({"ok": False, "errors": errors})
        return 1

    for index, existing in enumerate(edges):
        if existing.get("id") == args.edge_id:
            edges[index] = updated
            break
    if args.write:
        write_memory_graph(vault, edges)
    print_json({"ok": True, "written": bool(args.write), "outcome": args.outcome, "edge": updated})
    return 0


def command_self_correct(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    edges = load_edges_for_route(vault)
    failed = find_edge(edges, args.failed_edge_id)
    if failed is None:
        print_json({"ok": False, "errors": [f"failed edge not found: {args.failed_edge_id}"]})
        return 2

    corrected = find_edge(edges, args.corrected_edge_id)
    if corrected is None:
        corrected = base_edge(
            args.corrected_edge_id,
            args.from_text,
            args.to_text,
            "preferred_tool_for",
            args.action,
            args.evidence,
            weight=0.65,
        )
        edges.append(corrected)

    failed_updated = suppress_edge(failed, args.evidence, args.failure_signature)
    corrected_updated = apply_outcome(corrected, "success", args.evidence)
    corrected_updated["relation"] = "preferred_tool_for"
    corrected_updated["confidence"] = "verified-by-use"

    errors = validate_memory_edge_or_error(failed_updated) + validate_memory_edge_or_error(corrected_updated)
    if errors:
        print_json({"ok": False, "errors": errors})
        return 1

    for index, existing in enumerate(edges):
        if existing.get("id") == args.failed_edge_id:
            edges[index] = failed_updated
        if existing.get("id") == args.corrected_edge_id:
            edges[index] = corrected_updated
    if args.write:
        write_memory_graph(vault, edges)
    print_json(
        {
            "ok": True,
            "written": bool(args.write),
            "failed_edge": failed_updated,
            "corrected_edge": corrected_updated,
        }
    )
    return 0


def command_decay(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    now = parse_datetime(args.now) if args.now else datetime.now(timezone.utc)
    edges = load_edges_for_route(vault)
    proposed_changes: list[dict[str, Any]] = []

    for index, edge in enumerate(edges):
        last_used = edge.get("last_used")
        if not last_used:
            continue
        try:
            age_days = (now - parse_datetime(str(last_used))).days
        except ValueError:
            continue
        if age_days < args.days_unused:
            continue
        before_weight = float(edge.get("weight", 0))
        after_weight = round(max(0.0, before_weight - args.amount), 3)
        after_state = decay_state_for_weight(after_weight)
        change = {
            "id": edge.get("id"),
            "days_unused": age_days,
            "before_weight": round(before_weight, 3),
            "after_weight": after_weight,
            "before_state": edge.get("decay_state"),
            "after_state": after_state,
        }
        proposed_changes.append(change)
        if args.write:
            updated = deepcopy(edge)
            updated["weight"] = after_weight
            updated["decay_state"] = after_state
            updated["confidence"] = "suppressed" if after_state == "suppress" else "stale"
            if after_state == "suppress":
                updated["relation"] = "suppress"
            edges[index] = updated

    if args.write:
        write_memory_graph(vault, edges)
    print_json({"ok": True, "written": bool(args.write), "proposed_changes": proposed_changes})
    return 0


def command_explain_edge(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    edge = find_edge(load_edges_for_route(vault), args.edge_id)
    if edge is None:
        print_json({"ok": False, "errors": [f"edge not found: {args.edge_id}"]})
        return 2

    why = (
        f"This edge maps '{edge.get('from')}' to '{edge.get('to')}' with relation "
        f"{edge.get('relation')}, weight {edge.get('weight')}, confidence {edge.get('confidence')}, "
        f"and decay state {edge.get('decay_state')}."
    )
    print_json(
        {
            "ok": True,
            "edge": edge,
            "why": why,
            "evidence": edge.get("evidence", []),
            "interruption_policy": edge.get(
                "interruption_policy",
                "Treat route memory as guidance; verify evidence before external writes.",
            ),
        }
    )
    return 0


def route_to_text(route: dict[str, Any]) -> str:
    parts: list[str] = []
    if route.get("capability"):
        parts.append(str(route["capability"]))
    gates = route.get("gates") or []
    if gates:
        parts.extend(str(gate) for gate in gates)
    return " -> ".join(parts) or "momo-tools route"


def command_ingest_momo_route(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    source_path = Path(args.route_json).expanduser().resolve()
    data = json.loads(source_path.read_text(encoding="utf-8"))
    route = data.get("route", {})
    verification = data.get("verification", {})
    capture_info = data.get("second_brain_capture", {})

    status = str(verification.get("status", "unknown"))
    outcome = "success" if status in {"verified-working", "passed", "success"} else "failure"
    event_type = capture_info.get("type") or ("route-worked" if outcome == "success" else "route-failed")
    edge_id = capture_info.get("candidate_edge") or f"edge_{slugify(str(route.get('capability', 'momo-route')), 'momo-route')}"
    evidence = list(verification.get("evidence", [])) or [str(source_path)]
    evidence = append_unique(evidence, [str(source_path)])

    capture_event = {
        "id": f"capture_{compact_utc_id()}_{slugify(edge_id, 'momo-route')}",
        "timestamp": utc_now(),
        "type": event_type,
        "summary": f"momo-tools route result for: {data.get('task', 'unspecified task')}",
        "route": route_to_text(route),
        "outcome": status,
        "evidence": evidence,
        "privacy": "public-safe",
        "dry_run_first": not args.write,
    }

    capture_errors, _engine = validate_against_json_schema(capture_event, "capture-event.schema.json", "momo-route:capture")
    if capture_errors:
        print_json({"ok": False, "errors": capture_errors})
        return 1

    edges = load_edges_for_route(vault)
    edge = find_edge(edges, edge_id)
    if edge is None:
        edge = base_edge(
            edge_id,
            "momo-tools route result verification outcome",
            "capture event -> memory edge update -> future route suggestion",
            "evidence_chain",
            "Translate verified route results into capture events before strengthening memory graph edges.",
            evidence,
            weight=0.6,
        )
        edges.append(edge)
    updated = apply_outcome(
        edge,
        outcome,
        evidence,
        None if outcome == "success" else f"momo route status: {status}",
    )
    edge_errors = validate_memory_edge_or_error(updated)
    if edge_errors:
        print_json({"ok": False, "errors": edge_errors})
        return 1
    for index, existing in enumerate(edges):
        if existing.get("id") == edge_id:
            edges[index] = updated
            break

    if args.write:
        write_jsonl_append(vault / "captures.jsonl", capture_event)
        write_memory_graph(vault, edges)
    print_json(
        {
            "ok": True,
            "written": bool(args.write),
            "capture_event": capture_event,
            "edge": updated,
        }
    )
    return 0


def score_edge(query: str, edge: dict[str, Any]) -> float:
    if edge.get("relation") == "suppress" or edge.get("decay_state") == "suppress":
        return -1
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
            "score": round(score_edge(args.query, edge), 3),
        }
        for edge in ranked[: args.limit]
        if score_edge(args.query, edge) > 0
    ]
    print_json({"query": args.query, "suggestions": suggestions})
    return 0 if suggestions else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="second-brain")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create minimal AI-first vault skeleton")
    init_parser.add_argument("vault", help="target vault directory")
    init_parser.add_argument("--force", action="store_true", help="overwrite generated files")
    init_parser.set_defaults(func=command_init)

    validate_parser = subparsers.add_parser("validate", help="validate startup files and JSONL fixtures")
    validate_parser.add_argument("vault", help="vault directory")
    validate_parser.set_defaults(func=command_validate)

    capture_parser = subparsers.add_parser("capture", help="create capture event; dry-run unless --write is set")
    capture_parser.add_argument("--vault", default=".", help="vault directory")
    capture_parser.add_argument("--type", required=True, choices=sorted(VALID_CAPTURE_TYPES))
    capture_parser.add_argument("--summary", required=True)
    capture_parser.add_argument("--evidence", action="append", default=[])
    capture_parser.add_argument("--route")
    capture_parser.add_argument("--outcome")
    capture_parser.add_argument("--privacy", choices=sorted(VALID_PRIVACY), default="unknown")
    capture_parser.add_argument("--write", action="store_true", help="append event to captures.jsonl")
    capture_parser.set_defaults(func=command_capture)

    consolidate_parser = subparsers.add_parser("consolidate", help="produce safe consolidation report")
    consolidate_parser.add_argument("vault", help="vault directory")
    consolidate_parser.add_argument("--dry-run", action="store_true", help="report only")
    consolidate_parser.add_argument("--write", action="store_true", help="reserved future use; no destructive writes")
    consolidate_parser.set_defaults(func=command_consolidate)

    record_parser = subparsers.add_parser("record-outcome", help="reinforce or weaken a memory edge")
    record_parser.add_argument("vault", help="vault directory")
    record_parser.add_argument("--edge-id", required=True)
    record_parser.add_argument("--outcome", required=True, choices=["success", "failure"])
    record_parser.add_argument("--from", dest="from_text")
    record_parser.add_argument("--to", dest="to_text")
    record_parser.add_argument("--relation", choices=sorted(VALID_RELATIONS), default="preferred_tool_for")
    record_parser.add_argument("--action")
    record_parser.add_argument("--evidence", action="append", default=[])
    record_parser.add_argument("--failure-signature")
    record_parser.add_argument("--write", action="store_true")
    record_parser.set_defaults(func=command_record_outcome)

    correct_parser = subparsers.add_parser("self-correct", help="suppress a failed edge and reinforce a corrected route")
    correct_parser.add_argument("vault", help="vault directory")
    correct_parser.add_argument("--failed-edge-id", required=True)
    correct_parser.add_argument("--corrected-edge-id", required=True)
    correct_parser.add_argument("--from", dest="from_text", required=True)
    correct_parser.add_argument("--to", dest="to_text", required=True)
    correct_parser.add_argument("--action", required=True)
    correct_parser.add_argument("--evidence", action="append", default=[])
    correct_parser.add_argument("--failure-signature")
    correct_parser.add_argument("--write", action="store_true")
    correct_parser.set_defaults(func=command_self_correct)

    decay_parser = subparsers.add_parser("decay", help="lower weights for old unused memory edges")
    decay_parser.add_argument("vault", help="vault directory")
    decay_parser.add_argument("--days-unused", type=int, default=30)
    decay_parser.add_argument("--amount", type=float, default=0.1)
    decay_parser.add_argument("--now", help="ISO date-time for deterministic tests")
    decay_parser.add_argument("--write", action="store_true")
    decay_parser.set_defaults(func=command_decay)

    explain_parser = subparsers.add_parser("explain-edge", help="explain why a memory edge may be selected")
    explain_parser.add_argument("vault", help="vault directory")
    explain_parser.add_argument("edge_id")
    explain_parser.set_defaults(func=command_explain_edge)

    momo_parser = subparsers.add_parser("ingest-momo-route", help="convert a momo-tools route result into memory feedback")
    momo_parser.add_argument("vault", help="vault directory")
    momo_parser.add_argument("route_json", help="momo-tools route result JSON")
    momo_parser.add_argument("--write", action="store_true")
    momo_parser.set_defaults(func=command_ingest_momo_route)

    route_parser = subparsers.add_parser("route-suggest", help="suggest route memory graph edges")
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
