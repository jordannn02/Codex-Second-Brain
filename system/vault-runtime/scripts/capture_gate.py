#!/usr/bin/env python3
"""Plan constrained vault captures without mutating the vault."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ai_first_schema_audit import audit as run_ai_first_audit
from ai_first_schema_audit import FRONTMATTER_RE


MODE_BUDGETS = {
    "AUTO_CAPTURE": 0,
    "EXPLICIT_COMMAND": 1,
    "EXPLICIT_MAINTENANCE": 5,
    "WEEKLY_CONSOLIDATION": None,
}
SCHEMA_POLICY = ".codex/fixtures/ai_first_schema_policy.json"
SCHEMA_RUNNER = ".codex/scripts/ai_first_schema_audit.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, help="Vault root")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--mode", choices=sorted(MODE_BUDGETS))
    action.add_argument("--verify-token", help="Verify post-write schema deltas from a planning token")
    parser.add_argument("--target", action="append", default=[], help="Relative Markdown target")
    parser.add_argument("--artifact-format", choices=["okf"], help="Validate exact _export/okf Markdown artifacts instead of durable notes")
    parser.add_argument("--delivery-complete", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Required safety marker for planning")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def validate_target(vault: Path, raw_target: str) -> tuple[str | None, str | None]:
    target = Path(raw_target)
    if target.is_absolute() or ".." in target.parts:
        return None, "target_outside_vault"
    if not target.name or not target.suffix:
        return None, "target_not_file"
    try:
        (vault / target).resolve().relative_to(vault.resolve())
    except ValueError:
        return None, "target_outside_vault"
    return target.as_posix(), None


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_okf_target(vault: Path, raw_target: str) -> tuple[str | None, str | None]:
    target, error = validate_target(vault, raw_target)
    if error:
        return None, error
    relative = Path(target)
    if relative.parts[:2] != ("_export", "okf") or len(relative.parts) < 3 or relative.suffix != ".md":
        return None, "okf_target_outside_export_root"
    current = vault
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None, "okf_target_symlink"
    return target, None


def okf_blockers(vault: Path, targets: list[str]) -> set[str]:
    """Check only declared derived artifacts; never waive source-note schema."""
    blockers: set[str] = set()
    export_root = vault / "_export" / "okf"
    for target in targets:
        path = vault / target
        # The exporter preserves the source log verbatim, rather than inventing metadata.
        if target == "_export/okf/log.md":
            source = vault / "log.md"
            _, error = validate_target(vault, "log.md")
            if error or source.is_symlink() or not source.is_file() or path.read_bytes() != source.read_bytes():
                blockers.add(f"{target}:copied_log_mismatch")
            continue
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        if not match:
            blockers.add(f"{target}:missing_okf_frontmatter")
            continue
        # The exporter emits one-line JSON/YAML scalars, lists and an ISO timestamp.
        # Parse that exact subset, rejecting malformed YAML and null/bool metadata.
        fields = {}
        try:
            for line in match.group(1).splitlines():
                if not line.strip():
                    continue
                field = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*):[ \t]+(.*)", line)
                if not field or field[1] in fields:
                    raise ValueError("invalid or duplicate metadata field")
                key, raw = field.groups()
                raw = raw.strip()
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError:
                    if key != "timestamp" and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_ ./-]*", raw):
                        raise ValueError("invalid exported scalar")
                    value = None if raw.lower() in {"null", "~", "true", "false", "yes", "no", "on", "off"} else raw
                fields[key] = value
        except ValueError:
            blockers.add(f"{target}:invalid_okf_frontmatter")
            continue
        for key in ("type", "title", "timestamp"):
            if not isinstance(fields.get(key), str) or not fields[key].strip():
                blockers.add(f"{target}:missing_okf_{key}")
        if isinstance(fields.get("timestamp"), str):
            try:
                stamp = datetime.fromisoformat(fields["timestamp"])
                if stamp.tzinfo is None:
                    raise ValueError("timezone required")
            except ValueError:
                blockers.add(f"{target}:invalid_okf_timestamp")
        # Ignore code examples; remote/source URLs are preserved, not fetched.
        body = re.sub(r"(?ms)^```[^\n]*\n.*?^```[^\n]*$", "", text[match.end():])
        body = re.sub(r"`[^`\n]*`", "", body)
        destinations = re.findall(r"\[[^\]]*\]\((?:<([^>]+)>|([^\)\n]+))\)", body)
        references = {}
        for label, angle, plain in re.findall(r"(?m)^ {0,3}\[([^\]]+)\]:[ \t]*(?:<([^>]+)>|(\S+))", body):
            if label.startswith("^"):
                continue  # Obsidian footnote definitions are prose, not link destinations.
            references[label.strip().casefold()] = (angle, plain)
            destinations.append((angle, plain))
        for label, reference in re.findall(r"\[([^\]]+)\]\[([^\]]*)\]", body):
            if (reference or label).strip().casefold() not in references:
                blockers.add(f"{target}:okf_link_reference_missing:{reference or label}")
        for angle, plain in destinations:
            href = angle or re.sub(r"\s+[\"'].*[\"']$", "", plain)
            address = urlsplit(href)
            if address.scheme or address.netloc or href.startswith("#"):
                continue
            linked = (path.parent / unquote(href.split("#", 1)[0])).resolve()
            try:
                linked.relative_to(export_root)
            except ValueError:
                blockers.add(f"{target}:okf_link_outside_bundle")
                continue
            if not linked.is_file():
                blockers.add(f"{target}:okf_link_target_missing:{href}")
    return blockers


def load_policy(vault: Path) -> tuple[Path, dict[str, object]]:
    path = vault / SCHEMA_POLICY
    if not path.is_file():
        path = Path(__file__).resolve().parent / "fixtures" / "ai_first_schema_policy.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def blocker_set(vault: Path, policy: dict[str, object], targets: list[str]) -> set[str]:
    markdown = [target for target in targets if Path(target).suffix.lower() == ".md"]
    if not markdown:
        return set()
    payload = run_ai_first_audit(vault, policy, "core", markdown)
    return {str(blocker) for blocker in payload["blockers"]}


def encode_verification_token(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_verification_token(token: str) -> dict[str, object]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid verification token") from error
    if payload.get("schema") != "capture-verification-token/v1":
        raise ValueError("unsupported verification token schema")
    return payload


def verify_capture(vault: Path, token: str) -> dict[str, object]:
    baseline = decode_verification_token(token)
    targets = baseline.get("targets")
    baseline_blockers = baseline.get("baseline_blockers")
    if not isinstance(targets, list) or not all(isinstance(target, str) for target in targets):
        raise ValueError("verification token requires targets")
    if not isinstance(baseline_blockers, list) or not all(isinstance(item, str) for item in baseline_blockers):
        raise ValueError("verification token requires baseline blockers")
    if baseline.get("vault") != str(vault.resolve()):
        raise ValueError("invalid vault binding")
    if not targets or len(set(targets)) != len(targets):
        raise ValueError("empty or duplicate targets")
    for target in targets:
        normalized, error = validate_target(vault, target)
        if error or normalized != target or Path(target).suffix.lower() != ".md":
            raise ValueError("invalid verification target")
    artifact_format = baseline.get("artifact_format")
    if artifact_format is not None:
        if artifact_format != "okf" or baseline.get("vault") != str(vault.resolve()):
            raise ValueError("invalid artifact format or vault binding")
        if not targets or len(targets) > MODE_BUDGETS["EXPLICIT_MAINTENANCE"] or len(set(targets)) != len(targets):
            raise ValueError("invalid artifact target budget or duplicate targets")
        for target in targets:
            _, error = validate_okf_target(vault, target)
            if error:
                raise ValueError(f"invalid artifact target: {target}:{error}")
    missing = [target for target in targets if not (vault / target).is_file()]
    if missing:
        raise ValueError(f"post-write targets not found: {', '.join(missing)}")
    policy_path, policy = load_policy(vault)
    if file_sha256(policy_path) != baseline.get("policy_sha256"):
        return {
            "schema": "capture-post-write-validation/v1",
            "passed": False,
            "reasons": ["schema_policy_changed"],
            "targets": targets,
            "new_blockers": [],
            "resolved_blockers": [],
        }
    if artifact_format == "okf":
        blockers = sorted(okf_blockers(vault, targets))
        return {
            "schema": "capture-post-write-validation/v1",
            "artifact_format": "okf",
            "passed": not blockers,
            "reasons": [] if not blockers else ["artifact_validation_failed"],
            "targets": targets,
            "new_blockers": blockers,
            "resolved_blockers": [],
        }
    current = blocker_set(vault, policy, targets)
    previous = set(baseline_blockers)
    new_blockers = sorted(current - previous)
    return {
        "schema": "capture-post-write-validation/v1",
        "passed": not new_blockers,
        "reasons": [] if not new_blockers else ["schema_regression"],
        "targets": targets,
        "new_blockers": new_blockers,
        "resolved_blockers": sorted(previous - current),
        "remaining_blockers": sorted(current & previous),
    }


def plan_capture(
    vault: Path, mode: str, targets: list[str], delivery_complete: bool, dry_run: bool,
    artifact_format: str | None = None,
) -> dict[str, object]:
    reasons: list[str] = []
    normalized: list[str] = []
    rejected: list[dict[str, str]] = []
    budget = MODE_BUDGETS[mode]

    if artifact_format is not None:
        if artifact_format != "okf" or mode not in {"EXPLICIT_COMMAND", "EXPLICIT_MAINTENANCE"}:
            reasons.append("artifact_requires_explicit_command")
        if not targets or len(set(targets)) != len(targets):
            reasons.append("artifact_targets_empty_or_duplicate")

    if mode == "AUTO_CAPTURE":
        reasons.append("automatic_capture_not_authorized")
    if not targets or len(set(targets)) != len(targets):
        reasons.append("targets_empty_or_duplicate")
    if not dry_run:
        reasons.append("dry_run_required")
    if budget is not None and len(targets) > budget:
        reasons.append("target_budget_exceeded")

    for raw_target in targets:
        target, error = (validate_okf_target if artifact_format else validate_target)(vault, raw_target)
        if error:
            rejected.append({"target": raw_target, "reason": error})
        elif Path(target).suffix.lower() != ".md":
            rejected.append({"target": raw_target, "reason": "target_not_markdown"})
        else:
            normalized.append(target)
    if rejected:
        reasons.append("invalid_target")

    allowed = not reasons
    markdown_targets = [target for target in normalized if Path(target).suffix.lower() == ".md"] if allowed and not artifact_format else []
    strict_targets = [target for target in markdown_targets if not (vault / target).is_file()]
    delta_targets = [target for target in markdown_targets if (vault / target).is_file()]
    artifact_targets = (normalized if artifact_format else [target for target in normalized if Path(target).suffix.lower() != ".md"]) if allowed else []
    validation_targets = artifact_targets if artifact_format else markdown_targets
    verification_token = ""
    validation_command: list[str] = []
    if allowed and validation_targets:
        policy_path, policy = load_policy(vault)
        baseline = blocker_set(vault, policy, delta_targets)
        verification_token = encode_verification_token(
            {
                "schema": "capture-verification-token/v1",
                "targets": validation_targets,
                "baseline_blockers": sorted(baseline),
                "policy_sha256": file_sha256(policy_path),
                "vault": str(vault.resolve()),
                **({"artifact_format": artifact_format} if artifact_format else {}),
            }
        )
        validation_command = [
            "python3",
            ".codex/scripts/capture_gate.py",
            "--path",
            ".",
            "--verify-token",
            verification_token,
            "--json",
        ]
    manifest = {
        "schema": "capture-change-manifest/v1",
        "mode": mode,
        "dry_run": dry_run,
        "delivery_complete": delivery_complete,
        "target_budget": budget,
        "proposed_changes": normalized if allowed else [],
        "rejected_changes": rejected,
        "artifact_format": artifact_format,
        "post_write_schema_validation": {
            "mode": "okf-artifact" if artifact_format else "strict-new-delta-existing",
            "required": bool(validation_targets),
            "strict_targets": strict_targets,
            "delta_targets": delta_targets,
            "report_only_targets": delta_targets,
            "artifact_targets": artifact_targets,
            "verification_token": verification_token,
            "command": validation_command,
            "rule": ("Validate declared OKF artifacts, metadata and local links; a copied log must match its source."
                     if artifact_format else "Block new-note schema violations and any blocker newly introduced into an existing note; preserve pre-existing legacy debt as report-only."),
        },
    }
    return {"allowed": allowed, "reasons": reasons, "manifest": manifest}


def main() -> int:
    args = parse_args()
    vault = Path(args.path).expanduser().resolve()
    if not vault.is_dir():
        raise SystemExit(f"Vault directory not found: {vault}")
    try:
        if args.verify_token:
            result = verify_capture(vault, args.verify_token)
            exit_code = 0 if result["passed"] else 1
        else:
            result = plan_capture(vault, args.mode, args.target, args.delivery_complete, args.dry_run, args.artifact_format)
            if result["allowed"]:
                exit_code = 0
            elif "invalid_target" in result["reasons"]:
                exit_code = 2
            else:
                exit_code = 1
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        result = {"schema": "capture-gate-error/v1", "allowed": False, "error": str(error)}
        exit_code = 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        passed = result.get("allowed", result.get("passed", False))
        print("allowed" if passed else "blocked")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
