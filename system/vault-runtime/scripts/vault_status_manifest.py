#!/usr/bin/env python3
"""Produce a typed, read-only vault status manifest from executable checks."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_first_schema_audit import audit as run_ai_first_audit
from content_hygiene_audit import audit as run_content_hygiene_audit
from index_freshness import inspect_index
from retrieval_benchmark import load_acceptance, load_cases, run_benchmark
from vault_health import SCOPE_PROFILES, run_health_check


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=".", help="Vault root")
    parser.add_argument("--cases", required=True, help="Retrieval benchmark case file")
    parser.add_argument("--scope", default="core", choices=sorted(SCOPE_PROFILES))
    parser.add_argument("--ai-first-policy", required=True, help="AI-first schema policy JSON")
    parser.add_argument("--ttl-hours", type=int, default=168)
    parser.add_argument("--output", help="Explicit JSON output path; parent must already exist")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as temp:
        temp.write(encoded)
        temp.flush()
        os.fsync(temp.fileno())
        temporary_path = Path(temp.name)
    try:
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)


def build_manifest(
    vault: Path,
    cases_path: Path,
    policy_path: Path,
    scope: str,
    ttl_hours: int,
) -> dict[str, object]:
    if ttl_hours <= 0:
        raise ValueError("ttl-hours must be positive")
    observed = datetime.now(timezone.utc)
    with contextlib.redirect_stderr(io.StringIO()):
        health = run_health_check(vault, SCOPE_PROFILES[scope])
    benchmark = run_benchmark(vault, load_cases(cases_path), scope, load_acceptance(cases_path))
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    ai_first = run_ai_first_audit(vault, policy, scope)
    hygiene = run_content_hygiene_audit(vault, scope)
    index_freshness = inspect_index(vault, policy_path)
    ai_first_runner = Path(__file__).with_name("ai_first_schema_audit.py")
    health_issues = int(health["total_issues"])
    failed_cases = [str(case["id"]) for case in benchmark["cases"] if not case["passed"]]
    failed_cases.extend(str(blocker) for blocker in benchmark["acceptance"]["blockers"])
    components = [
        {
            "id": "vault-health",
            "level": "verified-working" if health_issues == 0 else "degraded",
            "scope": scope,
            "version": health["runner_sha256"],
            "observed_at": observed.isoformat(),
            "evidence_refs": [health["runner"]],
            "checks": [{"id": "health-runner", "passed": True, "finding_count": health_issues}],
            "blockers": [] if health_issues == 0 else [f"health_findings:{health_issues}"],
        },
        {
            "id": "retrieval-benchmark",
            "level": "verified-working" if not failed_cases else "degraded",
            "scope": scope,
            "version": benchmark["corpus"]["sha256"],
            "observed_at": observed.isoformat(),
            "evidence_refs": [benchmark["runner"]],
            "checks": [{"id": str(case["id"]), "passed": bool(case["passed"])} for case in benchmark["cases"]],
            "blockers": failed_cases,
        },
        {
            "id": "ai-first-schema",
            "level": ai_first["level"],
            "scope": scope,
            "version": file_sha256(ai_first_runner),
            "policy_sha256": file_sha256(policy_path),
            "observed_at": observed.isoformat(),
            "evidence_refs": ["vault-local:.codex/scripts/ai_first_schema_audit.py", str(policy_path)],
            "checks": [
                {"id": "schema-validation", "passed": not bool(ai_first["blockers"]), "stats": ai_first["stats"]}
            ],
            "findings": ai_first["blockers"],
            "blockers": ai_first["blockers"] if ai_first["level"] == "blocked" else [],
        },
        {
            "id": "content-hygiene",
            "level": hygiene["level"],
            "scope": scope,
            "version": file_sha256(Path(__file__).with_name("content_hygiene_audit.py")),
            "observed_at": observed.isoformat(),
            "evidence_refs": ["vault-local:.codex/scripts/content_hygiene_audit.py"],
            "checks": [
                {"id": "scaffolds-and-duplicates", "passed": not bool(hygiene["blockers"]), "stats": hygiene["stats"]}
            ],
            "blockers": hygiene["blockers"],
        },
        {
            "id": "index-freshness",
            "level": index_freshness["level"],
            "scope": "startup-index",
            "version": file_sha256(Path(__file__).with_name("index_freshness.py")),
            "observed_at": observed.isoformat(),
            "evidence_refs": ["vault-local:.codex/scripts/index_freshness.py", "index.md"],
            "checks": [
                {
                    "id": "generated-stats-current",
                    "passed": not bool(index_freshness["blockers"]),
                    "stats": index_freshness["stats"],
                }
            ],
            "blockers": index_freshness["blockers"],
        },
    ]
    if any(component["level"] == "blocked" for component in components):
        overall_level = "blocked"
    elif all(component["level"] == "verified-working" for component in components):
        overall_level = "verified-working"
    else:
        overall_level = "degraded"
    return {
        "schema": "vault-status-manifest/v1",
        "observed_at": observed.isoformat(),
        "valid_until": (observed + timedelta(hours=ttl_hours)).isoformat(),
        "ttl_hours": ttl_hours,
        "vault": str(vault),
        "scope": scope,
        "level": overall_level,
        "input_fingerprint": {
            "scope": scope,
            "corpus_sha256": benchmark["corpus"]["sha256"],
            "cases_sha256": file_sha256(cases_path),
            "policy_sha256": file_sha256(policy_path),
        },
        "components": components,
    }


def main() -> int:
    args = parse_args()
    vault = Path(args.path).expanduser().resolve()
    cases_path = Path(args.cases).expanduser().resolve()
    policy_path = Path(args.ai_first_policy).expanduser().resolve()
    if not vault.is_dir():
        raise SystemExit(f"Vault directory not found: {vault}")
    if not cases_path.is_file():
        raise SystemExit(f"Benchmark cases not found: {cases_path}")
    if not policy_path.is_file():
        raise SystemExit(f"AI-first policy not found: {policy_path}")
    manifest = build_manifest(vault, cases_path, policy_path, args.scope, args.ttl_hours)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        if not output.parent.is_dir():
            raise SystemExit(f"Output parent directory not found: {output.parent}")
        atomic_write_json(output, manifest)
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(manifest["level"])
    blocking_components = [
        component
        for component in manifest["components"]
        if component["level"] == "blocked"
        or (component["id"] == "retrieval-benchmark" and component["blockers"])
    ]
    return 0 if not blocking_components else 1


if __name__ == "__main__":
    raise SystemExit(main())
