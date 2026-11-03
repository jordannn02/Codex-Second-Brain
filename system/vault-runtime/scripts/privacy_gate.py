#!/usr/bin/env python3
"""Enforce vault privacy contexts and file-role allowlists before sharing."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, help="Vault root")
    parser.add_argument("--policy", required=True)
    parser.add_argument("--context", required=True, choices=["local", "rollout", "external"])
    parser.add_argument("--phase", default="plan", choices=["plan", "release"])
    parser.add_argument("--role", required=True)
    parser.add_argument("--target", action="append", required=True)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def scan_secret_patterns(path: Path, policy: dict[str, object]) -> list[str]:
    scan_policy = policy.get("content_scan", {})
    if not isinstance(scan_policy, dict):
        raise ValueError("content_scan policy must be an object")
    max_bytes = int(scan_policy.get("max_file_bytes", 2_000_000))
    if path.stat().st_size > max_bytes:
        return ["file_exceeds_scan_limit"]
    text = path.read_text(encoding="utf-8", errors="replace")
    findings: list[str] = []
    for row in scan_policy.get("patterns", []):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not isinstance(row.get("regex"), str):
            raise ValueError("content_scan patterns require id and regex")
        if re.search(row["regex"], text, re.MULTILINE):
            findings.append(row["id"])
    return sorted(set(findings))


def decision(
    vault: Path,
    target: str,
    role: str,
    context: str,
    phase: str,
    policy: dict[str, object],
) -> dict[str, object]:
    candidate = (vault / target).resolve()
    try:
        relative = candidate.relative_to(vault)
    except ValueError:
        return {"target": target, "decision": "deny", "reason": "target_escapes_vault"}
    contexts = policy["contexts"]
    allowed_roles = contexts[context]["allowed_roles"]
    if role not in allowed_roles:
        return {"target": target, "resolved": str(relative), "decision": "deny", "reason": "role_not_allowed_in_context"}
    roots = policy.get("role_roots", {}).get(role, [])
    if roots and not any(relative == Path(root) or Path(root) in relative.parents for root in roots):
        return {"target": target, "resolved": str(relative), "decision": "deny", "reason": "target_not_in_role_allowlist"}
    if phase == "release" and context in {"rollout", "external"}:
        if not candidate.is_file():
            return {
                "target": target,
                "resolved": str(relative),
                "decision": "deny",
                "reason": "release_target_not_file",
                "findings": [],
            }
        findings = scan_secret_patterns(candidate, policy)
        if findings:
            return {
                "target": target,
                "resolved": str(relative),
                "decision": "deny",
                "reason": "secret_pattern_detected",
                "findings": findings,
            }
        return {
            "target": target,
            "resolved": str(relative),
            "decision": "allow",
            "reason": "policy_allow_content_scanned",
            "findings": [],
        }
    return {"target": target, "resolved": str(relative), "decision": "allow", "reason": "policy_allow"}


def main() -> int:
    try:
        parsed = args()
        vault = Path(parsed.path).expanduser().resolve()
        policy = json.loads(Path(parsed.policy).expanduser().read_text(encoding="utf-8"))
        decisions = [decision(vault, target, parsed.role, parsed.context, parsed.phase, policy) for target in parsed.target]
        payload = {"schema": "privacy-gate/v2", "context": parsed.context, "phase": parsed.phase, "role": parsed.role, "allowed": all(row["decision"] == "allow" for row in decisions), "decisions": decisions}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["allowed"] else 1
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"schema": "privacy-gate/v2", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
