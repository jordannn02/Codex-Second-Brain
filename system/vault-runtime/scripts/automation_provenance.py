#!/usr/bin/env python3
"""Maintain an atomic append-only provenance ledger for automation runs."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import tempfile
import uuid
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


SCHEMA = "automation-run-provenance/v1"
REPORT_SCHEMA = "automation-provenance-report/v1"
TRIGGERS = {"scheduled", "manual", "retry"}
STATUSES = {"completed", "failed", "aborted", "blocked"}


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def parse_cost(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        cost = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("cost_usd must be a decimal") from error
    if cost < 0:
        raise ValueError("cost_usd must not be negative")
    return float(cost)


def build_record(args: argparse.Namespace) -> dict[str, object]:
    if args.trigger == "retry" and not args.retry_of:
        raise ValueError("retry_requires_retry_of")
    started = parse_time(args.started_at)
    finished = parse_time(args.finished_at)
    if finished < started:
        raise ValueError("finished_at_must_not_precede_started_at")
    cost = parse_cost(args.cost_usd)
    runner_sha256 = args.runner_sha256.lower()
    if len(runner_sha256) != 64 or any(char not in "0123456789abcdef" for char in runner_sha256):
        raise ValueError("runner_sha256_must_be_64_hex")
    return {
        "schema": SCHEMA,
        "run_id": str(uuid.uuid4()),
        "automation_id": args.automation_id,
        "trigger": args.trigger,
        "retry_of": args.retry_of,
        "status": args.status,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_ms": int((finished - started).total_seconds() * 1000),
        "runner": args.runner,
        "runner_sha256": runner_sha256,
        "cost_usd": cost,
        "cost_state": "known" if cost is not None else "unknown",
        "atomic_write": True,
    }


def append_record(path: Path, record: dict[str, object]) -> None:
    if not path.parent.is_dir():
        raise ValueError(f"ledger_parent_not_found:{path.parent}")
    lock_path = path.with_name(path.name + ".lock")
    encoded = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing = path.read_bytes() if path.exists() else b""
        if existing and not existing.endswith(b"\n"):
            raise ValueError("ledger_must_end_with_newline")
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as temp:
            temp.write(existing)
            temp.write(encoded)
            temp.flush()
            os.fsync(temp.fileno())
            temp_path = Path(temp.name)
        os.replace(temp_path, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"ledger_not_found:{path}")
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid_ledger_json_line:{number}") from error
        if record.get("schema") != SCHEMA:
            raise ValueError(f"invalid_ledger_schema_line:{number}")
        records.append(record)
    return records


def build_report(records: list[dict[str, Any]], ledger: Path) -> dict[str, object]:
    trigger_counts = Counter(str(record["trigger"]) for record in records)
    status_counts = Counter(str(record["status"]) for record in records)
    retry_counts = Counter(
        str(record["status"]) for record in records if record.get("trigger") == "retry"
    )
    known_costs = [Decimal(str(record["cost_usd"])) for record in records if record.get("cost_usd") is not None]
    return {
        "schema": REPORT_SCHEMA,
        "ledger": str(ledger),
        "ledger_sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
        "summary": {
            "run_count": len(records),
            "duration_ms": sum(int(record["duration_ms"]) for record in records),
            "known_cost_usd": float(sum(known_costs, Decimal("0"))),
            "unknown_cost_runs": sum(1 for record in records if record.get("cost_usd") is None),
        },
        "triggers": {trigger: trigger_counts[trigger] for trigger in sorted(trigger_counts)},
        "statuses": {status: status_counts[status] for status in sorted(status_counts)},
        "retry": {
            "run_count": sum(retry_counts.values()),
            "completed": retry_counts["completed"],
            "failed": retry_counts["failed"],
            "aborted": retry_counts["aborted"],
            "blocked": retry_counts["blocked"],
        },
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="command", required=True)
    append = subparsers.add_parser("append")
    append.add_argument("--ledger", required=True)
    append.add_argument("--automation-id", required=True)
    append.add_argument("--trigger", required=True, choices=sorted(TRIGGERS))
    append.add_argument("--retry-of")
    append.add_argument("--status", required=True, choices=sorted(STATUSES))
    append.add_argument("--started-at", required=True)
    append.add_argument("--finished-at", required=True)
    append.add_argument("--runner", required=True)
    append.add_argument("--runner-sha256", required=True)
    append.add_argument("--cost-usd")
    append.add_argument("--json", action="store_true")
    report = subparsers.add_parser("report")
    report.add_argument("--ledger", required=True)
    report.add_argument("--json", action="store_true")
    return root


def emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    try:
        args = parser().parse_args()
        ledger = Path(args.ledger).expanduser().resolve()
        if args.command == "append":
            payload = build_record(args)
            append_record(ledger, payload)
        else:
            payload = build_report(load_records(ledger), ledger)
        emit(payload)
        return 0
    except ValueError as error:
        emit({"schema": SCHEMA, "error": str(error)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
