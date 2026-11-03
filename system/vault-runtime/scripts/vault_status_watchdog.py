#!/usr/bin/env python3
"""Downgrade an expired typed vault status manifest without mutating it."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from retrieval_benchmark import corpus_sha256, load_corpus
from vault_health import SCOPE_PROFILES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Path to vault-status-manifest JSON")
    parser.add_argument("--path", required=True, help="Vault root used to recompute the current corpus fingerprint")
    parser.add_argument("--scope", choices=sorted(SCOPE_PROFILES), help="Override manifest scope")
    parser.add_argument("--cases", help="Benchmark cases file used by the status manifest")
    parser.add_argument("--ai-first-policy", help="AI-first policy file used by the status manifest")
    parser.add_argument("--now", help="ISO-8601 time override for deterministic checks")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_input_fingerprint(
    vault: Path,
    scope: str,
    cases_path: Path | None = None,
    policy_path: Path | None = None,
) -> dict[str, str]:
    fingerprint = {
        "scope": scope,
        "corpus_sha256": corpus_sha256(load_corpus(vault, scope)),
    }
    if cases_path is not None:
        fingerprint["cases_sha256"] = file_sha256(cases_path)
    if policy_path is not None:
        fingerprint["policy_sha256"] = file_sha256(policy_path)
    return fingerprint


def inspect(
    manifest: dict[str, object],
    now: datetime,
    current_fingerprint: dict[str, str],
) -> dict[str, object]:
    valid_until = manifest.get("valid_until")
    if not isinstance(valid_until, str):
        raise ValueError("manifest requires valid_until")
    expiry = parse_time(valid_until)
    expired = now >= expiry
    expected = manifest.get("input_fingerprint")
    fingerprint_valid = isinstance(expected, dict) and all(
        current_fingerprint.get(str(key)) == value for key, value in expected.items()
    )
    blockers: list[str] = []
    if expired:
        blockers.append("status_ttl_expired")
    if not fingerprint_valid:
        blockers.append("status_input_fingerprint_mismatch")
    return {
        "schema": "vault-status-watchdog/v1",
        "manifest_schema": manifest.get("schema"),
        "observed_at": now.isoformat(),
        "valid_until": expiry.isoformat(),
        "expired": expired,
        "input_changed": not fingerprint_valid,
        "expected_input_fingerprint": expected,
        "current_input_fingerprint": current_fingerprint,
        "level": "blocked" if blockers else manifest.get("level", "unknown"),
        "blockers": blockers,
    }


def main() -> int:
    args = parse_args()
    path = Path(args.manifest).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"Status manifest not found: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    vault = Path(args.path).expanduser().resolve()
    if not vault.is_dir():
        raise SystemExit(f"Vault directory not found: {vault}")
    expected = manifest.get("input_fingerprint")
    manifest_scope = expected.get("scope") if isinstance(expected, dict) else manifest.get("scope")
    scope = args.scope or manifest_scope
    if not isinstance(scope, str) or scope not in SCOPE_PROFILES:
        raise SystemExit("Status manifest requires a valid scope")
    cases_path = Path(args.cases).expanduser().resolve() if args.cases else None
    policy_path = Path(args.ai_first_policy).expanduser().resolve() if args.ai_first_policy else None
    for label, dependency in (("Benchmark cases", cases_path), ("AI-first policy", policy_path)):
        if dependency is not None and not dependency.is_file():
            raise SystemExit(f"{label} not found: {dependency}")
    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    fingerprint = current_input_fingerprint(vault, scope, cases_path, policy_path)
    payload = inspect(manifest, now, fingerprint)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["level"])
    return 1 if payload["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
