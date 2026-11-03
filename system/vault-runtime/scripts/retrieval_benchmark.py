#!/usr/bin/env python3
"""Run a read-only retrieval benchmark against a scoped Markdown corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from vault_health import SCOPE_PROFILES, iter_markdown


TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)
ASCII_TOKEN_RE = re.compile(r"[0-9A-Za-z_/-]+")
CJK_TOKEN_RE = re.compile(r"[\u3400-\u9fff]+")
DEFAULT_ACCEPTANCE = {
    "min_top1_success_rate": 0.7,
    "min_top3_success_rate": 0.95,
    "min_mrr": 0.8,
    "max_p95_case_elapsed_ms": 250.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=".", help="Vault root")
    parser.add_argument("--cases", required=True, help="JSON benchmark case file")
    parser.add_argument("--scope", default="core", choices=sorted(SCOPE_PROFILES))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def tokens(value: str) -> list[str]:
    lowered = value.casefold()
    found = [token for token in ASCII_TOKEN_RE.findall(lowered) if token]
    for sequence in CJK_TOKEN_RE.findall(lowered):
        found.append(sequence)
        for size in (2, 3, 4):
            found.extend(sequence[index : index + size] for index in range(len(sequence) - size + 1))
    return found


def load_corpus(vault: Path, scope: str) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    for path in sorted(iter_markdown(vault, SCOPE_PROFILES[scope])):
        relative = path.relative_to(vault).as_posix()
        notes.append({"path": relative, "content": path.read_text(encoding="utf-8")})
    return notes


def corpus_sha256(notes: list[dict[str, str]]) -> str:
    digest = hashlib.sha256()
    for note in notes:
        digest.update(note["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(note["content"].encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def rank(notes: list[dict[str, str]], query: str) -> list[dict[str, object]]:
    query_tokens = list(dict.fromkeys(tokens(query)))
    ranked: list[dict[str, object]] = []
    for note in notes:
        path = note["path"].casefold()
        content = note["content"].casefold()
        title_region = "\n".join(note["content"].splitlines()[:12]).casefold()
        matched = [token for token in query_tokens if token in path or token in content]
        coverage = len(matched) / len(query_tokens) if query_tokens else 0.0
        path_hits = sum(1 for token in query_tokens if token in path)
        title_hits = sum(1 for token in query_tokens if token in title_region)
        capped_term_frequency = sum(min(content.count(token), 3) for token in query_tokens)
        score = round(
            coverage * 100
            + path_hits * 12
            + title_hits * 5
            + math.log1p(capped_term_frequency) * 3,
            4,
        )
        if score:
            ranked.append({"path": note["path"], "score": score})
    return sorted(ranked, key=lambda hit: (-float(hit["score"]), str(hit["path"])))


def load_cases(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases JSON must contain a non-empty cases array")
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not isinstance(case.get("query"), str):
            raise ValueError("every case requires string id and query")
        if not isinstance(case.get("expect"), list) or not all(isinstance(path, str) for path in case["expect"]):
            raise ValueError("every case requires an expect path array")
        language = case.get("language", "unspecified")
        if language not in {"en", "zh", "unspecified"}:
            raise ValueError("case language must be en or zh")
        max_rank = case.get("max_rank", 5)
        if not isinstance(max_rank, int) or max_rank <= 0:
            raise ValueError("case max_rank must be a positive integer")
        case.setdefault("language", language)
        case.setdefault("max_rank", max_rank)
    return cases


def load_acceptance(path: Path) -> dict[str, float]:
    data = json.loads(path.read_text(encoding="utf-8"))
    configured = data.get("acceptance", {})
    if not isinstance(configured, dict):
        raise ValueError("acceptance must be an object")
    acceptance = dict(DEFAULT_ACCEPTANCE)
    for key in DEFAULT_ACCEPTANCE:
        if key in configured:
            value = configured[key]
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"acceptance {key} must be a non-negative number")
            acceptance[key] = float(value)
    for key in ("min_top1_success_rate", "min_top3_success_rate", "min_mrr"):
        if acceptance[key] > 1:
            raise ValueError(f"acceptance {key} must not exceed 1")
    return acceptance


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile_value + 0.999999)))
    return round(ordered[index], 3)


def run_benchmark(
    vault: Path,
    cases: list[dict[str, object]],
    scope: str,
    acceptance: dict[str, float] | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    corpus = load_corpus(vault, scope)
    results: list[dict[str, object]] = []
    for case in cases:
        case_started = time.perf_counter()
        hits = rank(corpus, str(case["query"]))
        expected = list(case["expect"])
        rank_by_path = {str(hit["path"]): index for index, hit in enumerate(hits, start=1)}
        expected_ranks = {path: rank_by_path.get(path) for path in expected}
        max_rank = int(case.get("max_rank", 5))
        missing = [path for path, rank_value in expected_ranks.items() if rank_value is None]
        too_low = [path for path, rank_value in expected_ranks.items() if rank_value is not None and rank_value > max_rank]
        passed = not missing and not too_low
        worst_rank = max((rank_value for rank_value in expected_ranks.values() if rank_value is not None), default=None)
        results.append(
            {
                "id": case["id"],
                "language": case.get("language", "unspecified"),
                "query": case["query"],
                "expect": expected,
                "max_rank": max_rank,
                "expected_ranks": expected_ranks,
                "worst_expected_rank": worst_rank,
                "hits": hits,
                "passed": passed,
                "failure_reason": None if passed else ("missing_expected" if missing else "rank_exceeded"),
                "elapsed_ms": round((time.perf_counter() - case_started) * 1000, 3),
            }
        )
    passed = sum(1 for result in results if result["passed"])
    total = len(results)
    top1 = sum(
        1
        for result in results
        if result["expected_ranks"] and all(rank_value is not None and rank_value <= 1 for rank_value in result["expected_ranks"].values())
    )
    top3 = sum(
        1
        for result in results
        if result["expected_ranks"] and all(rank_value is not None and rank_value <= 3 for rank_value in result["expected_ranks"].values())
    )
    reciprocal_ranks = [
        0.0 if result["worst_expected_rank"] is None else 1.0 / int(result["worst_expected_rank"])
        for result in results
    ]
    elapsed = [float(result["elapsed_ms"]) for result in results]
    summary = {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "success_rate": passed / total,
        "top1_success_rate": top1 / total,
        "top3_success_rate": top3 / total,
        "mrr": round(sum(reciprocal_ranks) / total, 6),
        "p95_case_elapsed_ms": percentile(elapsed, 0.95),
        "languages": {
            language: sum(1 for result in results if result["language"] == language)
            for language in sorted({str(result["language"]) for result in results})
        },
    }
    thresholds = acceptance or dict(DEFAULT_ACCEPTANCE)
    checks = {
        "top1_success_rate": summary["top1_success_rate"] >= thresholds["min_top1_success_rate"],
        "top3_success_rate": summary["top3_success_rate"] >= thresholds["min_top3_success_rate"],
        "mrr": summary["mrr"] >= thresholds["min_mrr"],
        "p95_case_elapsed_ms": summary["p95_case_elapsed_ms"] <= thresholds["max_p95_case_elapsed_ms"],
    }
    acceptance_result = {
        "passed": all(checks.values()),
        "thresholds": thresholds,
        "checks": checks,
        "blockers": [f"retrieval_acceptance_failed:{name}" for name, passed_check in checks.items() if not passed_check],
    }
    return {
        "schema": "retrieval-benchmark/v2",
        "runner": "vault-local:.codex/scripts/retrieval_benchmark.py",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "vault": str(vault),
        "scope": scope,
        "corpus": {
            "notes": len(corpus),
            "sha256": corpus_sha256(corpus),
            "paths": [note["path"] for note in corpus],
        },
        "cases": results,
        "summary": summary,
        "acceptance": acceptance_result,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def main() -> int:
    args = parse_args()
    vault = Path(args.path).expanduser().resolve()
    cases_path = Path(args.cases).expanduser().resolve()
    if not vault.is_dir():
        raise SystemExit(f"Vault directory not found: {vault}")
    if not cases_path.is_file():
        raise SystemExit(f"Benchmark cases not found: {cases_path}")
    result = run_benchmark(vault, load_cases(cases_path), args.scope, load_acceptance(cases_path))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result['summary']['passed']}/{result['summary']['total']} cases passed")
    return 0 if result["summary"]["failed"] == 0 and result["acceptance"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
