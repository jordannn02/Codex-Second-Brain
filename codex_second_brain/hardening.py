"""Public-safe operational hardening primitives for Codex Second Brain OS.

The functions in this module deliberately operate on local paths supplied by
the caller. They never upload vault content and they keep destructive actions
out of scope. Tests use synthetic fixtures only.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tarfile
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


BACKUP_SCHEMA = "codex-second-brain-backup/v1"
MODE_BUDGETS = {
    "AUTO_CAPTURE": 1,
    "EXPLICIT_COMMAND": 5,
    "WEEKLY_CONSOLIDATION": 250,
}
IGNORED_PARTS = {
    ".git",
    ".obsidian",
    ".trash",
    "_trash",
    "_export",
    "__pycache__",
}
REQUIRED_STARTUP_FILES = ["_CLAUDE.md", "index.md", "Home.md", "CRITICAL_FACTS.md"]
UNCHECKED_TASK_RE = re.compile(r"^\s*[-*+]\s+\[\s\]\s+")
TASK_DATE_RE = re.compile(
    r"@\{(?P<braced>\d{4}-\d{2}-\d{2})\}"
    r"|📅\s*(?P<emoji>\d{4}-\d{2}-\d{2})"
    r"|\bdue:\s*(?P<due>\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
INDEX_STATS_RE = re.compile(r"<!--\s*second-brain-stats:\s*(\{.*?\})\s*-->")
ASCII_TOKEN_RE = re.compile(r"[0-9A-Za-z_/-]+")
CJK_TOKEN_RE = re.compile(r"[\u3400-\u9fff]+")
SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("github-fine-grained-token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("openai-token", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_time(value: str) -> datetime:
    return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _iter_files(root: Path, suffixes: set[str] | None = None) -> list[Path]:
    files: list[Path] = []
    if not root.exists():
        return files
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file() or IGNORED_PARTS.intersection(path.relative_to(root).parts):
            continue
        if suffixes is not None and path.suffix.lower() not in suffixes:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _corpus_sha256(root: Path, *, exclude: set[str] | None = None) -> str:
    excluded = exclude or set()
    digest = hashlib.sha256()
    for path in _iter_files(root, {".md"}):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def analyze_health(vault: Path, *, today: date | None = None) -> dict[str, Any]:
    """Return a read-only health summary and every overdue task anchor."""

    vault = vault.expanduser().resolve()
    current_day = today or date.today()
    missing = [name for name in REQUIRED_STARTUP_FILES if not (vault / name).is_file()]
    markdown = _iter_files(vault, {".md"})
    overdue: list[dict[str, Any]] = []
    invalid_task_dates: list[dict[str, Any]] = []
    unchecked_count = 0

    for path in markdown:
        for line_no, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(),
            1,
        ):
            if not UNCHECKED_TASK_RE.match(line):
                continue
            unchecked_count += 1
            for match in TASK_DATE_RE.finditer(line):
                raw_due = next(value for value in match.groupdict().values() if value)
                try:
                    due = date.fromisoformat(raw_due)
                except ValueError:
                    invalid_task_dates.append(
                        {
                            "path": path.relative_to(vault).as_posix(),
                            "line": line_no,
                            "due": raw_due,
                            "task": line.strip(),
                        }
                    )
                    continue
                if due < current_day:
                    overdue.append(
                        {
                            "path": path.relative_to(vault).as_posix(),
                            "line": line_no,
                            "due": raw_due,
                            "task": line.strip(),
                        }
                    )

    state = (
        "blocked"
        if missing
        else "degraded"
        if overdue or invalid_task_dates
        else "verified-working"
    )
    return {
        "schema": "second-brain-health/v1",
        "vault": str(vault),
        "state": state,
        "startup_missing": missing,
        "markdown_file_count": len(markdown),
        "unchecked_task_count": unchecked_count,
        "overdue_task_count": len(overdue),
        "overdue_tasks": overdue,
        "invalid_task_date_count": len(invalid_task_dates),
        "invalid_task_dates": invalid_task_dates,
        "corpus_sha256": _corpus_sha256(vault),
        "checked_for_date": current_day.isoformat(),
    }


def _normalize_target(vault: Path, raw_target: str) -> tuple[str | None, str | None]:
    candidate = Path(raw_target)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None, f"target must stay inside the vault: {raw_target}"
    if candidate.suffix.lower() != ".md":
        return None, f"target must be Markdown: {raw_target}"
    resolved = (vault / candidate).resolve()
    try:
        normalized = resolved.relative_to(vault.resolve()).as_posix()
    except ValueError:
        return None, f"target escapes the vault: {raw_target}"
    return normalized, None


def evaluate_capture_gate(
    vault: Path,
    mode: str,
    targets: Sequence[str],
    delivery_complete: bool,
) -> dict[str, Any]:
    """Validate a planned note write and fail closed on missing prerequisites."""

    vault = vault.expanduser().resolve()
    usage_errors: list[str] = []
    policy_errors: list[str] = []
    normalized: list[str] = []

    if not vault.is_dir():
        usage_errors.append(f"vault does not exist: {vault}")
    if mode not in MODE_BUDGETS:
        usage_errors.append(f"unknown capture mode: {mode}")
    for raw_target in targets:
        target, error = _normalize_target(vault, raw_target)
        if error:
            usage_errors.append(error)
        elif target and target not in normalized:
            normalized.append(target)

    if not targets:
        usage_errors.append("at least one target is required")
    if mode == "AUTO_CAPTURE" and not delivery_complete:
        policy_errors.append("AUTO_CAPTURE requires a completed user-visible delivery")
    budget = MODE_BUDGETS.get(mode)
    if budget is not None and len(normalized) > budget:
        policy_errors.append(f"target budget exceeded: {len(normalized)} > {budget}")

    errors = usage_errors + policy_errors
    exit_code = 2 if usage_errors else 1 if policy_errors else 0
    return {
        "schema": "second-brain-capture-gate/v1",
        "allowed": not errors,
        "exit_code": exit_code,
        "mode": mode,
        "target_budget": budget,
        "targets": normalized,
        "errors": errors,
    }


def input_fingerprint(
    vault: Path,
    *,
    cases: Path | None = None,
    policy: Path | None = None,
) -> dict[str, str]:
    """Fingerprint the corpus and optional benchmark/policy inputs."""

    vault = vault.expanduser().resolve()
    return {
        "corpus_sha256": _corpus_sha256(vault),
        "cases_sha256": _sha256(cases.expanduser().resolve()) if cases else "not-provided",
        "policy_sha256": _sha256(policy.expanduser().resolve()) if policy else "not-provided",
    }


def inspect_status(
    manifest: Mapping[str, Any],
    current_fingerprint: Mapping[str, str],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Demote a time-valid status when any input fingerprint has changed."""

    current_time = _utc(now or datetime.now(timezone.utc))
    valid_until_raw = manifest.get("valid_until")
    expired = True
    errors: list[str] = []
    if isinstance(valid_until_raw, str):
        try:
            expired = current_time > _parse_time(valid_until_raw)
        except ValueError:
            errors.append("valid_until is not a valid ISO date-time")
    else:
        errors.append("valid_until is missing")

    saved = manifest.get("input_fingerprint")
    if not isinstance(saved, Mapping):
        saved = {}
        errors.append("input_fingerprint is missing")
    changed_fields = [
        key
        for key, value in current_fingerprint.items()
        if saved.get(key) != value
    ]
    input_changed = bool(changed_fields)
    manifest_state = str(manifest.get("state", "verified-working"))
    if manifest_state not in {"verified-working", "degraded", "blocked"}:
        errors.append(f"unsupported manifest state: {manifest_state}")
    state = "blocked" if expired or input_changed or errors else manifest_state
    return {
        "schema": "second-brain-status-watch/v1",
        "state": state,
        "expired": expired,
        "input_changed": input_changed,
        "changed_fields": changed_fields,
        "errors": errors,
        "checked_at": current_time.isoformat(),
    }


def _tokens(value: str) -> list[str]:
    result = [token.lower() for token in ASCII_TOKEN_RE.findall(value)]
    for chunk in CJK_TOKEN_RE.findall(value):
        result.append(chunk)
        result.extend(chunk[index : index + 2] for index in range(max(0, len(chunk) - 1)))
    return [token for token in result if token]


def _retrieval_corpus(vault: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in _iter_files(vault, {".md"}):
        rows.append(
            {
                "path": path.relative_to(vault).as_posix(),
                "text": path.read_text(encoding="utf-8", errors="ignore"),
            }
        )
    return rows


def _rank_corpus(corpus: Sequence[Mapping[str, str]], query: str) -> list[dict[str, Any]]:
    query_lower = query.lower().strip()
    query_tokens = list(dict.fromkeys(_tokens(query)))
    ranked: list[dict[str, Any]] = []
    for row in corpus:
        path = row["path"]
        path_lower = path.lower()
        text_lower = row["text"].lower()
        score = 0.0
        if query_lower and query_lower in (path_lower + "\n" + text_lower):
            score += 12.0
        for token in query_tokens:
            if token in path_lower:
                score += 4.0
            occurrences = text_lower.count(token)
            score += min(occurrences, 4) * 1.5
        if score > 0:
            ranked.append({"path": path, "score": round(score, 3)})
    return sorted(ranked, key=lambda item: (-item["score"], item["path"]))


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def run_retrieval_benchmark(
    vault: Path,
    cases: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Run a small rank-aware benchmark over Markdown path and content."""

    vault = vault.expanduser().resolve()
    corpus = _retrieval_corpus(vault)
    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    reciprocal_ranks: list[float] = []

    for case in cases:
        query = str(case.get("query", "")).strip()
        expected_raw = case.get("expected", [])
        expected = {expected_raw} if isinstance(expected_raw, str) else {str(item) for item in expected_raw}
        started = time.perf_counter()
        ranked = _rank_corpus(corpus, query)
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)
        rank = next((index for index, row in enumerate(ranked, 1) if row["path"] in expected), None)
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        results.append(
            {
                "query": query,
                "expected": sorted(expected),
                "rank": rank,
                "top_paths": [row["path"] for row in ranked[:5]],
                "latency_ms": round(latency_ms, 3),
            }
        )

    total = len(results)
    top1 = sum(item["rank"] == 1 for item in results) / total if total else 0.0
    top3 = sum(item["rank"] is not None and item["rank"] <= 3 for item in results) / total if total else 0.0
    mrr = sum(reciprocal_ranks) / total if total else 0.0
    return {
        "schema": "second-brain-retrieval-benchmark/v1",
        "vault": str(vault),
        "case_count": total,
        "corpus_count": len(corpus),
        "corpus_sha256": _corpus_sha256(vault),
        "metrics": {
            "top1": round(top1, 4),
            "top3": round(top3, 4),
            "mrr": round(mrr, 4),
            "p95_latency_ms": round(_percentile(latencies, 0.95), 3),
        },
        "cases": results,
    }


def vault_stats(vault: Path) -> dict[str, Any]:
    vault = vault.expanduser().resolve()
    markdown = _iter_files(vault, {".md"})
    return {
        "markdown_files": len(markdown),
        "dev_logs": sum(
            path.relative_to(vault).parts[:1] == ("Dev Logs",)
            for path in markdown
        ),
        "corpus_sha256": _corpus_sha256(vault, exclude={"index.md"}),
    }


def render_index_stats_marker(stats: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(stats), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"<!-- second-brain-stats: {payload} -->"


def check_index_freshness(index_path: Path, current_stats: Mapping[str, Any]) -> dict[str, Any]:
    text = index_path.read_text(encoding="utf-8", errors="ignore") if index_path.exists() else ""
    match = INDEX_STATS_RE.search(text)
    saved: dict[str, Any] | None = None
    errors: list[str] = []
    if match:
        try:
            loaded = json.loads(match.group(1))
            if isinstance(loaded, dict):
                saved = loaded
            else:
                errors.append("index stats marker must contain a JSON object")
        except json.JSONDecodeError as exc:
            errors.append(f"invalid index stats marker: {exc}")
    else:
        errors.append("index stats marker is missing")
    return {
        "current": saved == dict(current_stats) and not errors,
        "saved": saved,
        "actual": dict(current_stats),
        "errors": errors,
    }


def scan_sensitive_content(paths: Iterable[Path]) -> dict[str, Any]:
    """Scan file contents for high-confidence credential material."""

    findings: list[dict[str, Any]] = []
    scanned = 0
    for path in paths:
        path = path.expanduser().resolve()
        if not path.is_file():
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            for rule, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        {
                            "path": str(path),
                            "line": line_no,
                            "rule": rule,
                            "match": "<redacted>",
                        }
                    )
    return {
        "schema": "second-brain-privacy-scan/v1",
        "ok": not findings,
        "scanned_file_count": scanned,
        "findings": findings,
    }


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return rows, [f"ledger does not exist: {path}"]
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_no}: invalid JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {line_no}: expected JSON object")
            continue
        rows.append(value)
    return rows, errors


def validate_automation_ledger(path: Path, *, require_scheduled: bool = False) -> dict[str, Any]:
    rows, errors = _read_jsonl(path.expanduser().resolve())
    scheduled_successes: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        row_valid = True
        parsed_times: dict[str, datetime] = {}
        trigger = row.get("trigger")
        status = row.get("status")
        if trigger not in {"manual", "scheduled"}:
            errors.append(f"row {index}: trigger must be manual or scheduled")
            row_valid = False
        if status not in {"completed", "failed", "cancelled"}:
            errors.append(f"row {index}: unsupported status")
            row_valid = False
        for field in ["started_at", "finished_at"]:
            value = row.get(field)
            if not isinstance(value, str):
                errors.append(f"row {index}: {field} is required")
                row_valid = False
                continue
            try:
                parsed_times[field] = _parse_time(value)
            except ValueError:
                errors.append(f"row {index}: {field} is not an ISO date-time")
                row_valid = False
        if (
            "started_at" in parsed_times
            and "finished_at" in parsed_times
            and parsed_times["finished_at"] < parsed_times["started_at"]
        ):
            errors.append(f"row {index}: finished_at precedes started_at")
            row_valid = False
        if trigger == "scheduled" and status == "completed" and row_valid:
            scheduled_successes.append(row)
    if require_scheduled and not scheduled_successes:
        errors.append("scheduled_run_evidence_missing")
    return {
        "schema": "second-brain-automation-ledger/v1",
        "ok": not errors,
        "row_count": len(rows),
        "scheduled_success_count": len(scheduled_successes),
        "errors": errors,
    }


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_DIRECTORY)
        except (AttributeError, OSError):
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    """Write a JSON object with fsync plus atomic replacement."""

    _atomic_write(
        path.expanduser().resolve(),
        (json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def _backup_entries(
    vault: Path,
    external: Mapping[str, Path],
) -> list[tuple[Path, str, str]]:
    entries = [
        (path, f"vault/{path.relative_to(vault).as_posix()}", "vault")
        for path in _iter_files(vault)
    ]
    for label, source_value in sorted(external.items()):
        if not SAFE_LABEL_RE.fullmatch(label):
            raise ValueError(f"invalid external label: {label}")
        source = source_value.expanduser().resolve()
        if not source.exists():
            raise ValueError(f"external source does not exist: {source}")
        if source.is_file():
            entries.append((source, f"external/{label}/{source.name}", f"external:{label}"))
        else:
            for path in _iter_files(source):
                entries.append(
                    (
                        path,
                        f"external/{label}/{path.relative_to(source).as_posix()}",
                        f"external:{label}",
                    )
                )
    return sorted(entries, key=lambda item: item[1])


def create_backup(
    vault: Path,
    destination: Path,
    label: str,
    *,
    external: Mapping[str, Path] | None = None,
) -> Path:
    """Create a hashed snapshot without modifying the source vault."""

    vault = vault.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if not vault.is_dir():
        raise ValueError(f"vault does not exist: {vault}")
    if not SAFE_LABEL_RE.fullmatch(label):
        raise ValueError(f"invalid backup label: {label}")
    try:
        destination.relative_to(vault)
    except ValueError:
        pass
    else:
        raise ValueError("backup destination must be outside the source vault")
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    base = f"CodexSecondBrain-{label}-{stamp}"
    archive = destination / f"{base}.tar.gz"
    manifest_path = destination / f"{base}.manifest.json"
    entries = _backup_entries(vault, external or {})

    with tempfile.NamedTemporaryFile(dir=destination, prefix=archive.name + ".", delete=False) as handle:
        temporary_archive = Path(handle.name)
    try:
        with tarfile.open(temporary_archive, "w:gz") as tar:
            for source, archive_path, _kind in entries:
                tar.add(source, arcname=archive_path, recursive=False)
        with temporary_archive.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary_archive, archive)
    finally:
        temporary_archive.unlink(missing_ok=True)

    manifest = {
        "schema": BACKUP_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "archive": archive.name,
        "archive_sha256": _sha256(archive),
        "source_vault": str(vault),
        "files": [
            {
                "archive_path": archive_path,
                "source": kind,
                "sha256": _sha256(source),
                "size": source.stat().st_size,
            }
            for source, archive_path, kind in entries
        ],
    }
    write_json_atomic(manifest_path, manifest)
    return manifest_path


def _safe_extract(archive: Path, workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    root = workdir.resolve()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if member.issym() or member.islnk():
                raise ValueError(f"backup contains unsupported link: {member.name}")
            target = (root / member.name).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"backup path escapes restore root: {member.name}") from exc
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise ValueError(f"unable to read backup member: {member.name}")
            with source, target.open("wb") as output:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(chunk)


def verify_backup(manifest_path: Path, workdir: Path) -> dict[str, Any]:
    """Restore into an isolated directory and compare every recorded hash."""

    manifest_path = manifest_path.expanduser().resolve()
    workdir = workdir.expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("backup manifest must be a JSON object")
    if manifest.get("schema") != BACKUP_SCHEMA:
        raise ValueError("unsupported backup manifest schema")
    if "archive" not in manifest or not isinstance(manifest.get("files"), list):
        raise ValueError("backup manifest is missing archive or files")
    archive_name = Path(str(manifest["archive"]))
    if archive_name.is_absolute() or len(archive_name.parts) != 1:
        raise ValueError("backup archive must be adjacent to its manifest")
    archive = manifest_path.parent / archive_name
    source_vault = Path(str(manifest.get("source_vault", ""))).expanduser().resolve()
    try:
        workdir.relative_to(source_vault)
    except ValueError:
        pass
    else:
        raise ValueError("restore workdir must be outside the source vault")
    mismatches: list[str] = []
    if _sha256(archive) != manifest.get("archive_sha256"):
        mismatches.append("archive_sha256")
        return {"ok": False, "mismatches": mismatches, "restored_file_count": 0}
    if workdir.exists() and any(workdir.iterdir()):
        raise ValueError(f"restore workdir must be empty: {workdir}")
    _safe_extract(archive, workdir)
    for row in manifest["files"]:
        if not isinstance(row, Mapping) or "archive_path" not in row:
            mismatches.append("invalid-file-record")
            continue
        relative = str(row["archive_path"])
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            mismatches.append(f"unsafe-path:{relative}")
            continue
        restored = (workdir / relative_path).resolve()
        try:
            restored.relative_to(workdir)
        except ValueError:
            mismatches.append(f"unsafe-path:{relative}")
            continue
        if not restored.is_file():
            mismatches.append(f"missing:{relative}")
        elif _sha256(restored) != row.get("sha256"):
            mismatches.append(f"sha256:{relative}")
    return {
        "schema": "codex-second-brain-restore-verification/v1",
        "ok": not mismatches,
        "mismatches": mismatches,
        "restored_file_count": max(0, len(manifest["files"]) - len(mismatches)),
        "workdir": str(workdir),
    }


def audit_retention(
    policy: Mapping[str, Any],
    backup_times: Sequence[datetime],
    ledger_rows: Sequence[Mapping[str, Any]],
    status_manifest: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate backup, status, and scheduled-run freshness independently."""

    current = _utc(now or datetime.now(timezone.utc))
    issues: list[str] = []
    minimum_backups = int(policy.get("minimum_backup_count", 2))
    maximum_backup_age = float(policy.get("maximum_backup_age_days", 7))
    maximum_status_age = float(policy.get("maximum_status_age_hours", 24))
    require_scheduled = bool(policy.get("require_scheduled_success", True))
    maximum_scheduled_age = policy.get("maximum_scheduled_run_age_hours")

    normalized_backups = sorted((_utc(value) for value in backup_times), reverse=True)
    if len(normalized_backups) < minimum_backups:
        issues.append("backup_count_below_minimum")
    latest_backup_age_days: float | None = None
    if normalized_backups:
        latest_backup_age_days = (current - normalized_backups[0]).total_seconds() / 86400
        if latest_backup_age_days < 0:
            issues.append("backup_time_invalid")
        elif latest_backup_age_days > maximum_backup_age:
            issues.append("backup_too_old")
    else:
        issues.append("backup_evidence_missing")

    status_age_hours: float | None = None
    generated_at = status_manifest.get("generated_at")
    if isinstance(generated_at, str):
        try:
            status_age_hours = (current - _parse_time(generated_at)).total_seconds() / 3600
            if status_age_hours < 0:
                issues.append("status_manifest_time_invalid")
            elif status_age_hours > maximum_status_age:
                issues.append("status_manifest_too_old")
        except ValueError:
            issues.append("status_manifest_time_invalid")
    else:
        issues.append("status_manifest_missing")

    scheduled_candidates = [
        row
        for row in ledger_rows
        if row.get("trigger") == "scheduled" and row.get("status") == "completed"
    ]
    scheduled_successes: list[tuple[Mapping[str, Any], datetime]] = []
    for row in scheduled_candidates:
        finished_at = row.get("finished_at")
        if not isinstance(finished_at, str):
            continue
        try:
            finished = _parse_time(finished_at)
        except ValueError:
            continue
        if finished <= current:
            scheduled_successes.append((row, finished))
    if scheduled_candidates and not scheduled_successes:
        issues.append("scheduled_run_evidence_invalid")
    if require_scheduled and not scheduled_successes:
        issues.append("scheduled_run_evidence_missing")
    latest_scheduled_age_hours: float | None = None
    if scheduled_successes:
        latest_scheduled = max(value for _row, value in scheduled_successes)
        latest_scheduled_age_hours = (current - latest_scheduled).total_seconds() / 3600
        if (
            maximum_scheduled_age is not None
            and latest_scheduled_age_hours > float(maximum_scheduled_age)
        ):
            issues.append("scheduled_run_too_old")

    return {
        "schema": "second-brain-retention-audit/v1",
        "state": "verified-working" if not issues else "degraded",
        "issues": list(dict.fromkeys(issues)),
        "backup_count": len(normalized_backups),
        "latest_backup_age_days": round(latest_backup_age_days, 3) if latest_backup_age_days is not None else None,
        "status_age_hours": round(status_age_hours, 3) if status_age_hours is not None else None,
        "scheduled_success_count": len(scheduled_successes),
        "latest_scheduled_age_hours": (
            round(latest_scheduled_age_hours, 3)
            if latest_scheduled_age_hours is not None
            else None
        ),
        "checked_at": current.isoformat(),
    }
