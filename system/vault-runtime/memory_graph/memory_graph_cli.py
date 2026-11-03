#!/usr/bin/env python3
"""Edge-first memory graph CLI for CodexSecondBrain.

The implementation is intentionally local and non-destructive. It stores graph
edges in a JSONL sidecar, ranks routes, records feedback, exports evidence
packets, runs safe maintenance, and emits inspectable graph views.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from shadow_runtime import (
    DEFAULT_SHADOW_DB,
    ShadowStore,
    extract_safe_anchors,
    shadow_query_projection,
)


DEFAULT_EDGES = None

ALLOWED_RELATIONS = {
    "preferred_tool_for",
    "evidence_chain",
    "verified_by",
    "avoid_if",
    "superseded_by",
    "workflow_shortcut",
    "fallback_to",
    "state_action_edge",
    "used_edge",
}

ACTIONABLE_RELATIONS = {
    "preferred_tool_for",
    "state_action_edge",
    "workflow_shortcut",
    "fallback_to",
}

EVIDENCE_RELATIONS = {"evidence_chain", "verified_by"}

ASCII_TOKEN_RE = re.compile(r"[0-9A-Za-z_/\-.]+")
CJK_TOKEN_RE = re.compile(r"[\u3400-\u9fff]+")


def today() -> str:
    return dt.date.today().isoformat()


def cjk_ngrams(token: str, min_size: int = 2, max_size: int = 4) -> set[str]:
    grams: set[str] = set()
    for size in range(min_size, max_size + 1):
        if len(token) < size:
            continue
        grams.update(token[index : index + size] for index in range(len(token) - size + 1))
    return grams


def tokenize(text: str) -> set[str]:
    lowered = text.lower()
    tokens = set(ASCII_TOKEN_RE.findall(lowered))
    for token in CJK_TOKEN_RE.findall(lowered):
        tokens.add(token)
        tokens.update(cjk_ngrams(token))
    return {token for token in tokens if token}


def stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def edge_id(edge: dict[str, Any]) -> str:
    if edge.get("id"):
        return str(edge["id"])
    return stable_id(
        "edge",
        edge.get("from", ""),
        edge.get("to", ""),
        edge.get("relation", ""),
        edge.get("action", ""),
    )


def confidence_value(confidence: str) -> float:
    lowered = confidence.lower()
    if any(key in lowered for key in ("verified", "runtime", "db-backed", "test-backed")):
        return 1.0
    if any(key in lowered for key in ("source", "workflow-rule", "documented", "user-corrected")):
        return 0.94
    if "inferred" in lowered:
        return 0.78
    return 0.86


def state_for(edge: dict[str, Any]) -> str:
    weight = float(edge.get("weight", 0.0))
    fail_count = int(edge.get("fail_count", 0) or 0)
    success_count = int(edge.get("success_count", 0) or 0)
    if fail_count >= 2 and fail_count > success_count:
        return "suppress"
    if weight >= 0.85:
        return "hot"
    if weight >= 0.65:
        return "warm"
    if weight >= 0.25:
        return "cold"
    if weight > 0.15:
        return "stale"
    return "suppress"


def normalize_edge(edge: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(edge)
    normalized["id"] = edge_id(normalized)
    normalized.setdefault("relation", "workflow_shortcut")
    normalized.setdefault("weight", 0.5)
    normalized.setdefault("confidence", "inferred")
    normalized.setdefault("decay_state", state_for(normalized))
    normalized.setdefault("last_used", "")
    normalized.setdefault("use_count", 0)
    normalized.setdefault("success_count", 0)
    normalized.setdefault("fail_count", 0)
    normalized.setdefault("evidence", [])
    normalized.setdefault("action", "")
    normalized.setdefault("interruption_policy", "")
    return normalized


def edge_text(edge: dict[str, Any]) -> str:
    evidence = " ".join(str(item) for item in edge.get("evidence", []))
    tags = " ".join(str(item) for item in edge.get("tags", []))
    core = " ".join(
        str(edge.get(key, ""))
        for key in ("id", "from", "to", "relation", "confidence", "action", "interruption_policy")
    )
    return f"{core} {evidence} {tags}"


def score_edge(edge: dict[str, Any], query: str) -> tuple[float, list[str]]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return 0.0, []
    haystack = tokenize(edge_text(edge))
    matched = sorted(query_tokens & haystack)
    query_match = len(matched) / len(query_tokens)
    if query_match == 0:
        return 0.0, []

    weight = float(edge.get("weight", 0.0))
    confidence = confidence_value(str(edge.get("confidence", "")))
    use_count = int(edge.get("use_count", 0) or 0)
    success_count = int(edge.get("success_count", 0) or 0)
    fail_count = int(edge.get("fail_count", 0) or 0)
    recent_success = 1.0 + min(success_count, 6) * 0.02 - min(fail_count, 6) * 0.03
    workflow_fit = 1.05 if edge.get("relation") in {"preferred_tool_for", "state_action_edge"} else 1.0
    cost_saving = 1.05 if edge.get("action") else 1.0
    if edge.get("decay_state") == "suppress":
        cost_saving *= 0.25
    elif edge.get("decay_state") == "stale":
        cost_saving *= 0.55
    if edge.get("relation") == "avoid_if":
        cost_saving *= 0.7

    activation = query_match * weight * confidence * recent_success * workflow_fit * cost_saving
    if use_count == 0:
        activation *= 0.95
    return round(max(0.0, min(1.0, activation)), 4), matched


def load_edges(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    edges: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            edges.append(normalize_edge(json.loads(line)))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_number}: invalid JSONL: {exc}") from exc
    return edges


def save_edges(path: Path, edges: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(edge, ensure_ascii=False, separators=(",", ":")) for edge in edges)
    payload = (text + ("\n" if text else "")).encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as temporary:
        temporary.write(payload)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)


@contextlib.contextmanager
def locked_edges(path: Path):
    """Hold one exclusive lock across the complete load-modify-save transaction."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield load_edges(path)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def print_output(payload: Any, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, str):
        print(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def find_edge(edges: list[dict[str, Any]], edge_id_value: str) -> dict[str, Any]:
    for edge in edges:
        if edge.get("id") == edge_id_value:
            return edge
    raise SystemExit(f"Edge not found: {edge_id_value}")


def route(edges: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for edge in edges:
        activation_score, matched = score_edge(edge, query)
        if activation_score == 0:
            continue
        row = dict(edge)
        row["activation_score"] = activation_score
        row["matched_tokens"] = matched
        rows.append(row)
    rows.sort(key=lambda item: item["activation_score"], reverse=True)
    return rows[:limit]


def decision_tier(edge: dict[str, Any]) -> str:
    if edge.get("relation") == "avoid_if" or edge.get("decay_state") == "suppress":
        return "suppress"
    score = float(edge.get("activation_score", 0.0))
    if edge.get("relation") in ACTIONABLE_RELATIONS and edge.get("decay_state") == "hot" and score >= 0.70:
        return "direct"
    if score >= 0.45:
        return "preload"
    if score >= 0.15:
        return "searchable"
    return "ignore"


def route_plan_item(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "edge_id": edge["id"],
        "relation": edge.get("relation"),
        "decision_tier": decision_tier(edge),
        "activation_score": edge.get("activation_score", 0.0),
        "decay_state": edge.get("decay_state"),
        "action": edge.get("action", ""),
        "evidence": edge.get("evidence", []),
        "interruption_policy": edge.get("interruption_policy", ""),
        "matched_tokens": edge.get("matched_tokens", []),
    }


def bounded_counterfactual(
    matches: list[dict[str, Any]],
    max_items: int = 2,
    max_chars: int = 300,
) -> tuple[list[dict[str, Any]], str]:
    """Build inspectable suggestions that are never injected into task context."""

    item_limit = max(0, min(int(max_items), 2))
    char_limit = max(0, min(int(max_chars), 300))
    candidates: list[dict[str, Any]] = []
    preview_lines: list[str] = []
    preview_size = 0

    for match in matches:
        item = route_plan_item(match)
        if item["decision_tier"] in {"ignore", "suppress"}:
            continue
        candidate = {
            "edge_id": item["edge_id"],
            "relation": item["relation"],
            "score": item["activation_score"],
            "tier": item["decision_tier"],
        }
        action = re.sub(r"\s+", " ", str(item.get("action", ""))).strip()
        line = f"{candidate['edge_id']} [{candidate['tier']}] {action}".strip()
        separator = 1 if preview_lines else 0
        if len(candidates) >= item_limit or preview_size + separator + len(line) > char_limit:
            continue
        candidates.append(candidate)
        preview_lines.append(line)
        preview_size += separator + len(line)

    return candidates, "\n".join(preview_lines)


def record_outcome(edge: dict[str, Any], outcome: str) -> dict[str, Any]:
    edge["use_count"] = int(edge.get("use_count", 0) or 0) + 1
    edge["last_used"] = today()
    if outcome == "success":
        edge["success_count"] = int(edge.get("success_count", 0) or 0) + 1
        edge["weight"] = round(min(1.0, float(edge.get("weight", 0.0)) + 0.08), 4)
    else:
        edge["fail_count"] = int(edge.get("fail_count", 0) or 0) + 1
        edge["weight"] = round(max(0.0, float(edge.get("weight", 0.0)) - 0.08), 4)
    edge["decay_state"] = state_for(edge)
    return edge


def parse_date(value: str) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def decay_edges(
    edges: list[dict[str, Any]],
    days_unused: int,
    amount: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cutoff = dt.date.today() - dt.timedelta(days=days_unused)
    changed: list[dict[str, Any]] = []
    for edge in edges:
        before = {
            "id": edge["id"],
            "weight": edge.get("weight"),
            "decay_state": edge.get("decay_state"),
        }
        last_used = parse_date(str(edge.get("last_used", "")))
        if last_used is not None and last_used > cutoff:
            edge["decay_state"] = state_for(edge)
            continue
        if float(edge.get("weight", 0.0)) > 0:
            edge["weight"] = round(max(0.0, float(edge.get("weight", 0.0)) - amount), 4)
        if not edge.get("evidence") and edge.get("relation") not in {"avoid_if", "fallback_to", "used_edge"}:
            edge["decay_state"] = "stale"
        else:
            edge["decay_state"] = state_for(edge)
        after = {
            "id": edge["id"],
            "weight": edge.get("weight"),
            "decay_state": edge.get("decay_state"),
        }
        if before != after:
            changed.append({"before": before, "after": after})
    return edges, changed


def classify_anchor(anchor: str) -> str:
    lowered = anchor.lower()
    if any(marker in lowered for marker in (".md", "knowledge/", "critical_facts", "agents.md")):
        return "note"
    if any(marker in lowered for marker in (".xlsx", "workbook", "excel")):
        return "workbook"
    if any(marker in lowered for marker in ("select ", "sql", "database", "db ", "oracle")):
        return "sql"
    if any(marker in lowered for marker in ("runtime", "screen", "host", "t100 web")):
        return "runtime"
    if any(marker in lowered for marker in (".4gl", ".per", ".42m", "source", "codebase")):
        return "source"
    return "note"


def evidence_packet(edge: dict[str, Any], edges: list[dict[str, Any]]) -> dict[str, Any]:
    edge_from = str(edge.get("from", ""))
    edge_to = str(edge.get("to", ""))
    edge_id_value = str(edge.get("id", ""))
    related: list[dict[str, Any]] = []
    anchors: list[str] = []

    for anchor in edge.get("evidence", []):
        if str(anchor) not in anchors:
            anchors.append(str(anchor))

    for candidate in edges:
        if candidate["id"] == edge_id_value:
            continue
        touches_edge = edge_id_value in {str(candidate.get("from", "")), str(candidate.get("to", ""))}
        same_subject = edge_from in {str(candidate.get("from", "")), str(candidate.get("to", ""))}
        same_target = edge_to in {str(candidate.get("from", "")), str(candidate.get("to", ""))}
        if touches_edge or (candidate.get("relation") in EVIDENCE_RELATIONS and (same_subject or same_target)):
            related.append(candidate)
            for anchor in candidate.get("evidence", []):
                if str(anchor) not in anchors:
                    anchors.append(str(anchor))

    evidence_by_class: dict[str, list[str]] = {}
    for anchor in anchors:
        evidence_by_class.setdefault(classify_anchor(anchor), []).append(anchor)

    return {
        "anchors": anchors,
        "evidence_by_class": evidence_by_class,
        "related_edges": related,
        "boundary": "Anchors speed proof assembly but do not replace fresh source/runtime/DB verification when required.",
    }


def filtered_edges(edges: list[dict[str, Any]], min_weight: float, include_suppress: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for edge in edges:
        if float(edge.get("weight", 0.0)) < min_weight:
            continue
        if not include_suppress and edge.get("decay_state") == "suppress":
            continue
        rows.append(edge)
    return rows


def mermaid_graph(edges: list[dict[str, Any]]) -> str:
    lines = ["graph LR"]
    for edge in edges:
        source = str(edge.get("from", "")).replace('"', "'")
        target = str(edge.get("to", "")).replace('"', "'")
        relation = str(edge.get("relation", "")).replace('"', "'")
        weight = float(edge.get("weight", 0.0))
        lines.append(f'  "{source}" -- "{relation} ({weight:.2f})" --> "{target}"')
    return "\n".join(lines)


def graph_json(edges: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, str]] = {}
    json_edges: list[dict[str, Any]] = []
    for edge in edges:
        source = str(edge.get("from", ""))
        target = str(edge.get("to", ""))
        nodes.setdefault(source, {"id": source, "label": source})
        nodes.setdefault(target, {"id": target, "label": target})
        json_edges.append(
            {
                "id": edge["id"],
                "source": source,
                "target": target,
                "relation": edge.get("relation"),
                "weight": edge.get("weight"),
                "decay_state": edge.get("decay_state"),
            }
        )
    return {"nodes": list(nodes.values()), "edges": json_edges}


def cmd_route(args: argparse.Namespace) -> int:
    edges = load_edges(args.edges)
    print_output({"query": args.query, "matches": route(edges, args.query, args.limit)}, args.json)
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    edges = load_edges(args.edges)
    matches = route(edges, args.query, args.limit)
    plan: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for match in matches:
        item = route_plan_item(match)
        if item["decision_tier"] == "suppress":
            suppressed.append(item)
        elif item["decision_tier"] != "ignore":
            plan.append(item)
    payload = {
        "query": args.query,
        "session_id": args.session_id,
        "task_id": args.task_id,
        "route_plan": plan,
        "suppressed_matches": suppressed,
        "delivery_contract": {
            "primary_delivery_first": True,
            "deferred_until_after_delivery": [
                "record-session",
                "self-correct",
                "obsidian-save",
                "rule-promotion",
                "weekly-propagation",
            ],
            "rule": "Deliver the visible task first. Record or save only when explicitly authorized by the user or covered by an existing authorized maintenance workflow; success or failure alone never authorizes a write.",
        },
        "record_after_task": "Only with explicit save authorization or an existing authorized maintenance workflow: record-session --session-id ... --task-id ... --edge-id ... --outcome success|failure. Do not record automatically on success or failure.",
        "safety_boundary": "Routing guidance is advisory; destructive/production actions still need explicit verification and permission.",
    }
    print_output(payload, args.json)
    return 0


def cmd_shadow_observe(args: argparse.Namespace) -> int:
    """Evaluate the graph counterfactually without changing task behavior or edges."""

    effective_items = max(0, min(int(args.max_items), 2))
    effective_chars = max(0, min(int(args.max_chars), 300))
    anchors = extract_safe_anchors(args.query)
    projection = shadow_query_projection(args.query, anchors)
    edges = load_edges(args.edges)
    matches = route(edges, projection, max(effective_items * 4, 8)) if anchors else []
    candidates, preview = bounded_counterfactual(matches, effective_items, effective_chars)
    event = ShadowStore(args.shadow_db).record_observation(
        profile=args.profile,
        query=args.query,
        anchors=anchors,
        candidates=candidates,
        session_id=args.session_id,
        task_id=args.task_id,
    )
    print_output(
        {
            "mode": "shadow-only",
            "injection_enabled": False,
            "canonical_edge_write": False,
            "event_id": event["event_id"],
            "created_at": event["created_at"],
            "profile": event["profile"],
            "query_digest": event["query_digest"],
            "anchors": event["anchors"],
            "routing_projection": projection,
            "counterfactual_candidates": event["candidates"],
            "counterfactual_preview": preview,
            "budget": {"max_items": effective_items, "max_chars": effective_chars},
            "safety_boundary": (
                "Counterfactual output is recorded for evaluation only; it is not injected "
                "into the active task and cannot mutate canonical graph edges."
            ),
        },
        args.json,
    )
    return 0


def cmd_shadow_feedback(args: argparse.Namespace) -> int:
    try:
        feedback = ShadowStore(args.shadow_db).record_feedback(
            args.event_id,
            args.profile,
            args.verdict,
            args.seconds_saved,
            args.used_edge or [],
        )
    except LookupError as exc:
        raise SystemExit(str(exc)) from exc
    print_output({"mode": "shadow-only", "feedback": feedback}, args.json)
    return 0


def cmd_shadow_report(args: argparse.Namespace) -> int:
    report = ShadowStore(args.shadow_db).report(args.profile, args.days)
    print_output({"mode": "shadow-only", "injection_enabled": False, **report}, args.json)
    return 0


def cmd_shadow_maintenance(args: argparse.Namespace) -> int:
    result = ShadowStore(args.shadow_db).maintenance(args.retention_days, args.apply)
    print_output({"mode": "shadow-only", **result}, args.json)
    return 0


def cmd_record_use(args: argparse.Namespace) -> int:
    with locked_edges(args.edges) as edges:
        edge = find_edge(edges, args.edge_id)
        record_outcome(edge, args.outcome)
        save_edges(args.edges, edges)
    print_output({"edge": edge}, args.json)
    return 0


def attempt_edge_id(context: str, path: str, error: str) -> str:
    return stable_id("attempt_guard", context, path, error)


def find_attempt_edge(edges: list[dict[str, Any]], context: str, path: str, error: str) -> dict[str, Any] | None:
    edge_id_value = attempt_edge_id(context, path, error)
    for edge in edges:
        if edge.get("id") == edge_id_value:
            return edge
    return None


def build_attempt_edge(args: argparse.Namespace) -> dict[str, Any]:
    evidence = list(args.evidence or [])
    if args.error:
        evidence.append(f"error:{args.error}")
    succeeded = args.outcome == "success"
    return normalize_edge(
        {
            "id": attempt_edge_id(args.context, args.path, args.error),
            "from": args.context,
            "to": args.path,
            "relation": "workflow_shortcut" if succeeded else "avoid_if",
            "weight": 0.18 if args.outcome == "failure" else 0.65,
            "confidence": "attempt-observed",
            "decay_state": "suppress" if args.outcome == "failure" else "warm",
            "last_used": today(),
            "use_count": 1,
            "success_count": 1 if args.outcome == "success" else 0,
            "fail_count": 1 if args.outcome == "failure" else 0,
            "evidence": evidence,
            "action": (
                f"Reuse verified path `{args.path}` for `{args.context}` when the same conditions apply."
                if succeeded
                else f"Guard against repeating path `{args.path}` for `{args.context}` when error is `{args.error}`."
            ),
            "interruption_policy": (
                "Reverify when the environment, target, or automation schema changes."
                if succeeded
                else "Do not retry the same failed path unless new evidence, changed environment, or explicit user override exists."
            ),
        }
    )


def cmd_record_attempt(args: argparse.Namespace) -> int:
    with locked_edges(args.edges) as edges:
        edge = find_attempt_edge(edges, args.context, args.path, args.error)
        if edge is None:
            edge = build_attempt_edge(args)
            edges.append(edge)
        else:
            if args.evidence:
                existing = list(edge.get("evidence", []))
                for item in args.evidence:
                    if item not in existing:
                        existing.append(item)
                edge["evidence"] = existing
            record_outcome(edge, args.outcome)
        if args.outcome == "failure":
            edge["relation"] = "avoid_if"
            edge["decay_state"] = "suppress"
            edge["weight"] = min(float(edge.get("weight", 0.18)), 0.18)
        elif int(edge.get("fail_count", 0) or 0) == 0:
            edge["relation"] = "workflow_shortcut"
            edge["action"] = f"Reuse verified path `{args.path}` for `{args.context}` when the same conditions apply."
            edge["interruption_policy"] = "Reverify when the environment, target, or automation schema changes."
        save_edges(args.edges, edges)
    print_output({"attempt_edge": edge}, args.json)
    return 0


def cmd_attempt_guard(args: argparse.Namespace) -> int:
    edges = load_edges(args.edges)
    edge = find_attempt_edge(edges, args.context, args.path, args.error)
    failures = int(edge.get("fail_count", 0) or 0) if edge else 0
    suppressed = bool(edge and edge.get("decay_state") == "suppress")
    allowed = not edge or (failures < args.max_failures and not suppressed)
    payload = {
        "allowed": allowed,
        "context": args.context,
        "path": args.path,
        "error": args.error,
        "previous_failures": failures,
        "attempt_edge": edge,
        "suggested_action": (
            "Do not retry this same path. Use self-correct or choose a different verified route before continuing."
            if not allowed
            else "No matching failed path recorded; proceed only with normal verification boundaries."
        ),
        "override_boundary": "Only override when the environment changed, a new evidence anchor exists, or the user explicitly asks to retry.",
    }
    print_output(payload, args.json)
    return 0


def cmd_record_session(args: argparse.Namespace) -> int:
    updated_edges: list[dict[str, Any]] = []
    audit_edges: list[dict[str, Any]] = []
    session_node = f"session:{args.session_id}/task:{args.task_id}"
    with locked_edges(args.edges) as edges:
        for edge_id_value in args.edge_id:
            edge = find_edge(edges, edge_id_value)
            record_outcome(edge, args.outcome)
            updated_edges.append(edge)
            audit_edge = normalize_edge(
                {
                    "id": stable_id("used_edge", args.session_id, args.task_id, edge_id_value, args.outcome, args.note, today()),
                    "from": session_node,
                    "to": edge_id_value,
                    "relation": "used_edge",
                    "weight": 1.0,
                    "confidence": "session-audit",
                    "decay_state": "hot",
                    "last_used": today(),
                    "use_count": 1,
                    "success_count": 1 if args.outcome == "success" else 0,
                    "fail_count": 1 if args.outcome == "failure" else 0,
                    "evidence": [args.note] if args.note else [],
                    "action": f"Recorded {args.outcome} outcome for {edge_id_value}.",
                }
            )
            edges.append(audit_edge)
            audit_edges.append(audit_edge)
        save_edges(args.edges, edges)
    print_output({"updated_edges": updated_edges, "audit_edges": audit_edges}, args.json)
    return 0


def cmd_decay(args: argparse.Namespace) -> int:
    with locked_edges(args.edges) as edges:
        edges, changed = decay_edges(edges, args.days_unused, args.amount)
        save_edges(args.edges, edges)
    print_output({"changed": changed, "edges": edges}, args.json)
    return 0


def cmd_maintenance(args: argparse.Namespace) -> int:
    if args.dry_run:
        edges = load_edges(args.edges)
        working = [dict(edge) for edge in edges]
        updated, changed = decay_edges(working, args.days_unused, args.amount)
        protected_evidence_count = sum(1 for edge in edges if edge.get("evidence"))
    else:
        with locked_edges(args.edges) as edges:
            working = [dict(edge) for edge in edges]
            updated, changed = decay_edges(working, args.days_unused, args.amount)
            protected_evidence_count = sum(1 for edge in edges if edge.get("evidence"))
            save_edges(args.edges, updated)
    payload = {
        "dry_run": args.dry_run,
        "would_change": changed,
        "safety": {
            "delete_count": 0,
            "protected_evidence_count": protected_evidence_count,
            "policy": "Maintenance only adjusts weights/states; it never deletes evidence-bearing notes or edges.",
        },
    }
    print_output(payload, args.json)
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    edges = load_edges(args.edges)
    edge = find_edge(edges, args.edge_id)
    print_output({"edge": edge}, args.json)
    return 0


def gap_rows(edges: list[dict[str, Any]]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for edge in edges:
        if edge.get("relation") not in ALLOWED_RELATIONS:
            gaps.append({"id": str(edge["id"]), "issue": "unknown_relation"})
        if not edge.get("evidence") and edge.get("relation") not in {"used_edge"}:
            gaps.append({"id": str(edge["id"]), "issue": "missing_evidence"})
        if not edge.get("action") and edge.get("relation") in ACTIONABLE_RELATIONS:
            gaps.append({"id": str(edge["id"]), "issue": "missing_action"})
        if edge.get("decay_state") not in {"hot", "warm", "cold", "stale", "suppress"}:
            gaps.append({"id": str(edge["id"]), "issue": "unknown_decay_state"})
    return gaps


def cmd_gaps(args: argparse.Namespace) -> int:
    edges = load_edges(args.edges)
    print_output({"gaps": gap_rows(edges)}, args.json)
    return 0


def cmd_visualize(args: argparse.Namespace) -> int:
    edges = load_edges(args.edges)
    rows = filtered_edges(edges, args.min_weight, args.include_suppress)
    if args.format == "json":
        print_output(graph_json(rows), True)
    else:
        print_output(mermaid_graph(rows), False)
    return 0


def cmd_evidence_chain(args: argparse.Namespace) -> int:
    edges = load_edges(args.edges)
    edge = find_edge(edges, args.edge_id)
    packet = evidence_packet(edge, edges)
    if args.markdown:
        lines = [
            f"# Evidence Chain - {edge['id']}",
            "",
            f"- Relation: `{edge.get('relation')}`",
            f"- From: {edge.get('from')}",
            f"- To: {edge.get('to')}",
            f"- Action: {edge.get('action', '')}",
            "",
            "## Anchors",
        ]
        lines.extend(f"- {anchor}" for anchor in packet["anchors"])
        print_output("\n".join(lines), False)
    else:
        print_output({"edge": edge, "proof_packet": packet}, args.json)
    return 0


def cmd_self_correct(args: argparse.Namespace) -> int:
    if not args.evidence:
        raise SystemExit("self-correct requires at least one --evidence anchor")
    evidence = list(args.evidence)
    if args.session_id or args.task_id:
        evidence.append(f"session:{args.session_id or 'unknown'}/task:{args.task_id or 'unknown'}")
    with locked_edges(args.edges) as edges:
        wrong_edge = find_edge(edges, args.wrong_edge_id)
        record_outcome(wrong_edge, "failure")
        wrong_edge["decay_state"] = "suppress"
        avoid_edge = normalize_edge(
            {
                "id": stable_id("avoid_edge", args.condition, args.wrong_edge_id),
                "from": args.condition,
                "to": args.wrong_edge_id,
                "relation": "avoid_if",
                "weight": 0.18,
                "confidence": "self-correction",
                "decay_state": "suppress",
                "last_used": today(),
                "use_count": 1,
                "success_count": 0,
                "fail_count": 1,
                "evidence": evidence,
                "action": f"Avoid {args.wrong_edge_id} when {args.condition}.",
                "interruption_policy": "Review before suppressing if the wrong path is the only available path.",
            }
        )
        corrected_edge = normalize_edge(
            {
                "id": stable_id("corrected_edge", args.corrected_from, args.corrected_to, args.action),
                "from": args.corrected_from,
                "to": args.corrected_to,
                "relation": args.relation,
                "weight": args.weight,
                "confidence": "user-corrected-verified",
                "decay_state": "hot",
                "last_used": today(),
                "use_count": 1,
                "success_count": 1,
                "fail_count": 0,
                "evidence": evidence,
                "action": args.action,
                "interruption_policy": "Interrupt if root cause is unclear or correction would affect destructive/production behavior.",
            }
        )
        edges.append(avoid_edge)
        edges.append(corrected_edge)
        save_edges(args.edges, edges)
    print_output(
        {
            "wrong_edge": wrong_edge,
            "avoid_edge": avoid_edge,
            "corrected_edge": corrected_edge,
            "positive_feedback_rule": "Correction is learned only with a demoted wrong path and a verified corrected path.",
        },
        args.json,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edges", type=Path, required=True, help="Explicit graph JSONL path")
    parser.add_argument("--authorize-write", action="store_true", help="Confirm this invocation is authorized to persist data")
    parser.add_argument(
        "--shadow-db",
        type=Path,
        default=None,
        help="Machine-local SQLite evaluation store (never the canonical graph sidecar)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    route_parser = subparsers.add_parser("route", help="Rank edges for a query")
    route_parser.add_argument("query")
    route_parser.add_argument("--limit", type=int, default=5)
    route_parser.add_argument("--json", action="store_true")
    route_parser.set_defaults(func=cmd_route)

    preflight_parser = subparsers.add_parser("preflight", help="Return actionable startup routing plan")
    preflight_parser.add_argument("query")
    preflight_parser.add_argument("--session-id", default="")
    preflight_parser.add_argument("--task-id", default="")
    preflight_parser.add_argument("--limit", type=int, default=8)
    preflight_parser.add_argument("--json", action="store_true")
    preflight_parser.set_defaults(func=cmd_preflight)

    shadow_observe_parser = subparsers.add_parser(
        "shadow-observe",
        help="Record bounded counterfactual routing without injecting it into the task",
    )
    shadow_observe_parser.add_argument("query")
    shadow_observe_parser.add_argument("--profile", required=True)
    shadow_observe_parser.add_argument("--session-id", default="")
    shadow_observe_parser.add_argument("--task-id", default="")
    shadow_observe_parser.add_argument("--max-items", type=int, default=2)
    shadow_observe_parser.add_argument("--max-chars", type=int, default=300)
    shadow_observe_parser.add_argument("--json", action="store_true")
    shadow_observe_parser.set_defaults(func=cmd_shadow_observe)

    shadow_feedback_parser = subparsers.add_parser(
        "shadow-feedback",
        help="Attach profile-bound helpful, neutral, or harmful feedback",
    )
    shadow_feedback_parser.add_argument("event_id")
    shadow_feedback_parser.add_argument("--profile", required=True)
    shadow_feedback_parser.add_argument(
        "--verdict", choices=["helpful", "neutral", "harmful"], required=True
    )
    shadow_feedback_parser.add_argument("--seconds-saved", type=float, default=0.0)
    shadow_feedback_parser.add_argument("--used-edge", action="append")
    shadow_feedback_parser.add_argument("--json", action="store_true")
    shadow_feedback_parser.set_defaults(func=cmd_shadow_feedback)

    shadow_report_parser = subparsers.add_parser(
        "shadow-report",
        help="Evaluate a profile against the non-automatic influence-review gate",
    )
    shadow_report_parser.add_argument("--profile", required=True)
    shadow_report_parser.add_argument("--days", type=int, default=14)
    shadow_report_parser.add_argument("--json", action="store_true")
    shadow_report_parser.set_defaults(func=cmd_shadow_report)

    shadow_maintenance_parser = subparsers.add_parser(
        "shadow-maintenance",
        help="Preview or explicitly purge expired machine-local soft events",
    )
    shadow_maintenance_parser.add_argument("--retention-days", type=int, default=30)
    shadow_maintenance_parser.add_argument("--apply", action="store_true")
    shadow_maintenance_parser.add_argument("--json", action="store_true")
    shadow_maintenance_parser.set_defaults(func=cmd_shadow_maintenance)

    record_parser = subparsers.add_parser("record-use", help="Reinforce or suppress one edge")
    record_parser.add_argument("edge_id")
    record_parser.add_argument("--outcome", choices=["success", "failure"], required=True)
    record_parser.add_argument("--json", action="store_true")
    record_parser.set_defaults(func=cmd_record_use)

    attempt_record_parser = subparsers.add_parser("record-attempt", help="Record one generic process attempt outcome")
    attempt_record_parser.add_argument("--context", required=True)
    attempt_record_parser.add_argument("--path", required=True)
    attempt_record_parser.add_argument("--outcome", choices=["success", "failure"], required=True)
    attempt_record_parser.add_argument("--error", default="")
    attempt_record_parser.add_argument("--evidence", action="append")
    attempt_record_parser.add_argument("--json", action="store_true")
    attempt_record_parser.set_defaults(func=cmd_record_attempt)

    attempt_guard_parser = subparsers.add_parser("attempt-guard", help="Block repeated generic process attempts with the same failed signature")
    attempt_guard_parser.add_argument("--context", required=True)
    attempt_guard_parser.add_argument("--path", required=True)
    attempt_guard_parser.add_argument("--error", default="")
    attempt_guard_parser.add_argument("--max-failures", type=int, default=1)
    attempt_guard_parser.add_argument("--json", action="store_true")
    attempt_guard_parser.set_defaults(func=cmd_attempt_guard)

    session_parser = subparsers.add_parser("record-session", help="Record session outcome and append used_edge audit")
    session_parser.add_argument("--session-id", required=True)
    session_parser.add_argument("--task-id", required=True)
    session_parser.add_argument("--edge-id", action="append", required=True)
    session_parser.add_argument("--outcome", choices=["success", "failure"], required=True)
    session_parser.add_argument("--note", default="")
    session_parser.add_argument("--json", action="store_true")
    session_parser.set_defaults(func=cmd_record_session)

    self_correct_parser = subparsers.add_parser("self-correct", help="Demote a wrong path and add a verified corrected path")
    self_correct_parser.add_argument("--wrong-edge-id", required=True)
    self_correct_parser.add_argument("--condition", required=True)
    self_correct_parser.add_argument("--corrected-from", required=True)
    self_correct_parser.add_argument("--corrected-to", required=True)
    self_correct_parser.add_argument("--relation", default="state_action_edge", choices=sorted(ACTIONABLE_RELATIONS))
    self_correct_parser.add_argument("--weight", type=float, default=0.87)
    self_correct_parser.add_argument("--action", required=True)
    self_correct_parser.add_argument("--evidence", action="append", required=True)
    self_correct_parser.add_argument("--session-id", default="")
    self_correct_parser.add_argument("--task-id", default="")
    self_correct_parser.add_argument("--json", action="store_true")
    self_correct_parser.set_defaults(func=cmd_self_correct)

    decay_parser = subparsers.add_parser("decay", help="Lower unused edge priority")
    decay_parser.add_argument("--days-unused", type=int, default=30)
    decay_parser.add_argument("--amount", type=float, default=0.05)
    decay_parser.add_argument("--json", action="store_true")
    decay_parser.set_defaults(func=cmd_decay)

    maintenance_parser = subparsers.add_parser("maintenance", help="Safe weekly maintenance report or decay run")
    maintenance_parser.add_argument("--days-unused", type=int, default=30)
    maintenance_parser.add_argument("--amount", type=float, default=0.05)
    maintenance_parser.add_argument("--dry-run", action="store_true")
    maintenance_parser.add_argument("--json", action="store_true")
    maintenance_parser.set_defaults(func=cmd_maintenance)

    explain_parser = subparsers.add_parser("explain", help="Explain one edge")
    explain_parser.add_argument("edge_id")
    explain_parser.add_argument("--json", action="store_true")
    explain_parser.set_defaults(func=cmd_explain)

    gaps_parser = subparsers.add_parser("gaps", help="Report schema/evidence gaps")
    gaps_parser.add_argument("--json", action="store_true")
    gaps_parser.set_defaults(func=cmd_gaps)

    visualize_parser = subparsers.add_parser("visualize", help="Emit Mermaid or JSON graph")
    visualize_parser.add_argument("--format", choices=["mermaid", "json"], default="mermaid")
    visualize_parser.add_argument("--min-weight", type=float, default=0.0)
    visualize_parser.add_argument("--include-suppress", action="store_true")
    visualize_parser.set_defaults(func=cmd_visualize)

    evidence_parser = subparsers.add_parser("evidence-chain", help="Export proof packet for one edge")
    evidence_parser.add_argument("edge_id")
    evidence_parser.add_argument("--json", action="store_true")
    evidence_parser.add_argument("--markdown", action="store_true")
    evidence_parser.set_defaults(func=cmd_evidence_chain)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    shadow = args.command.startswith("shadow-")
    writes = args.command in {"record-use", "record-attempt", "record-session", "self-correct", "decay"} or (args.command == "maintenance" and not args.dry_run) or shadow
    if shadow and args.shadow_db is None:
        parser.error("shadow commands require an explicit --shadow-db path; even report initializes the store")
    if writes and not args.authorize_write:
        parser.error("this command persists data; --authorize-write requires explicit user save authorization or an existing authorized maintenance workflow")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
