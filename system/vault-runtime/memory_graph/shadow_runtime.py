"""Machine-local, non-canonical shadow telemetry for the memory graph.

The shadow store intentionally keeps raw prompts, session ids, task ids, paths,
and evidence text out of SQLite.  It records only digests, allowlisted anchors,
bounded semantic-edge candidates, and explicit evaluation outcomes.
"""

from __future__ import annotations

import datetime as dt
import contextlib
import hashlib
import hmac
import json
import os
import platform
import re
import sqlite3
import statistics
import threading
import time
import uuid
from pathlib import Path
from typing import Any


DEFAULT_SHADOW_DB = Path(
    os.environ.get(
        "CODEX_SECOND_BRAIN_SHADOW_DB",
        "~/.local/state/second-brain/shadow-events.db",
    )
).expanduser()

SAFE_CJK_TERMS = (
    "來源碼追蹤",
    "來源追蹤",
    "信用額度",
    "銷售訂單",
    "採購單",
    "程式規格",
    "會議記錄",
    "第二大腦",
    "證據鏈",
    "正式機",
    "來源碼",
    "開表",
    "欄位",
    "查詢",
    "修正",
    "部署",
    "記憶圖",
    "推理",
)

SAFE_TOOLS = {
    "codebase memory pro": "codebase-memory-pro",
    "markitdown": "markitdown",
    "sqlplus": "sqlplus",
    "obsidian": "obsidian",
    "codex": "codex",
}

TERM_PROJECTIONS = {
    "來源碼追蹤": "source tracing source code",
    "來源追蹤": "source tracing source code",
    "來源碼": "source tracing source code",
    "信用額度": "credit limit",
    "銷售訂單": "sales order",
    "採購單": "purchase order",
    "程式規格": "program specification",
    "會議記錄": "meeting notes",
    "第二大腦": "second brain",
    "證據鏈": "evidence chain",
    "正式機": "production host runtime",
    "開表": "table design schema",
    "欄位": "field schema",
    "查詢": "query sql",
    "修正": "correction",
    "部署": "deployment",
    "記憶圖": "memory graph",
    "推理": "reasoning",
}

PROFILE_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}\Z")
SAFE_EDGE_ID_RE = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
CANONICAL_EDGE_ID_RE = re.compile(
    r"(?:edge|used_edge|attempt_guard|avoid_edge|corrected_edge)_[A-Za-z0-9_.:-]{1,112}\Z"
)
SAFE_ANCHOR_RE = re.compile(
    r"(?:term|system|program|table|field|env|scope|error|tool|source):[^/@\\\s]{1,72}\Z"
)
PROGRAM_OR_FIELD_RE = re.compile(r"\b([a-z]{3,8})(\d{3,5})\b", re.IGNORECASE)
TABLE_RE = re.compile(r"\b[a-z][a-z0-9]{2,15}_t\b", re.IGNORECASE)
ENV_RE = re.compile(r"(?!)")
SCOPE_RE = re.compile(r"\b(?:ent=\d{1,6}|site=[a-z0-9_-]{1,12})\b", re.IGNORECASE)
ERROR_RE = re.compile(r"\b(?:ora|sp2)-\d{4,5}\b", re.IGNORECASE)
SOURCE_FILE_RE = re.compile(
    r"(?<![/\\])\b[a-z0-9_-]{2,32}\.(?:4gl|4fd|per|42m)\b",
    re.IGNORECASE,
)

_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}
_SCHEMA_INIT_ATTEMPTS = 6
_SCHEMA_INIT_RETRY_SECONDS = 0.05


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS shadow_meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shadow_events(
  event_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  profile TEXT NOT NULL,
  machine_digest TEXT NOT NULL,
  session_digest TEXT NOT NULL,
  task_digest TEXT NOT NULL,
  query_digest TEXT NOT NULL,
  anchors_json TEXT NOT NULL,
  candidates_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shadow_feedback(
  event_id TEXT PRIMARY KEY,
  profile TEXT NOT NULL,
  verdict TEXT NOT NULL,
  seconds_saved REAL NOT NULL,
  used_edges_json TEXT NOT NULL,
  feedback_at TEXT NOT NULL,
  FOREIGN KEY(event_id) REFERENCES shadow_events(event_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_shadow_profile_created
  ON shadow_events(profile, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_feedback_profile_verdict
  ON shadow_feedback(profile, verdict);
INSERT OR REPLACE INTO shadow_meta(key,value) VALUES('schema_version','2');
"""


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def cloud_synced_path(path: Path) -> bool:
    rendered = str(path.expanduser().resolve()).lower()
    markers = (
        "/mobile documents/",
        "/icloud drive/",
        "/dropbox/",
        "/onedrive/",
        "/google drive/",
    )
    return any(marker in rendered for marker in markers)


def migrate_inline_feedback(db: sqlite3.Connection) -> int:
    """Idempotently preserve feedback written by the pre-v2 staging schema."""

    columns = {
        str(row[1]) for row in db.execute("PRAGMA table_info(shadow_events)").fetchall()
    }
    legacy_columns = {"verdict", "seconds_saved", "used_edges_json", "feedback_at"}
    if not legacy_columns.issubset(columns):
        return 0
    before = db.total_changes
    db.execute(
        """INSERT OR IGNORE INTO shadow_feedback(
             event_id,profile,verdict,seconds_saved,used_edges_json,feedback_at
           )
           SELECT event_id,profile,verdict,COALESCE(seconds_saved,0),
                  COALESCE(used_edges_json,'[]'),feedback_at
           FROM shadow_events
           WHERE feedback_at IS NOT NULL
             AND verdict IN ('helpful','neutral','harmful')"""
    )
    return db.total_changes - before


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def keyed_digest(key: bytes, value: str) -> str:
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def load_or_create_key(path: Path) -> bytes:
    """Create a private per-store HMAC key without exposing it to the vault."""

    path.parent.mkdir(parents=True, exist_ok=True)
    secret = os.urandom(32)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        descriptor = None
    if descriptor is not None:
        try:
            os.write(descriptor, secret)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    for _ in range(50):
        try:
            stored = path.read_bytes()
        except FileNotFoundError:
            stored = b""
        if len(stored) >= 32:
            os.chmod(path, 0o600)
            return stored
        time.sleep(0.01)
    raise RuntimeError("shadow_hmac_key_unavailable")


def _profile(value: str) -> str:
    normalized = str(value).strip().lower()
    if not PROFILE_RE.fullmatch(normalized):
        raise ValueError("profile must be 1-32 lowercase letters, digits, underscore, or hyphen")
    return normalized


def _safe_edge_id(value: object, digest_value=digest) -> str:
    rendered = str(value or "")
    if SAFE_EDGE_ID_RE.fullmatch(rendered) and CANONICAL_EDGE_ID_RE.fullmatch(rendered):
        return rendered
    return "edge:" + digest_value(rendered)[:24]


def _safe_anchor(value: object) -> str | None:
    rendered = str(value or "").strip().lower()
    if not SAFE_ANCHOR_RE.fullmatch(rendered):
        return None
    kind, _, anchor_value = rendered.partition(":")
    if kind == "term" and anchor_value in SAFE_CJK_TERMS:
        return rendered
    if kind == "system" and anchor_value == "t100":
        return rendered
    if kind == "tool" and anchor_value in set(SAFE_TOOLS.values()):
        return rendered
    if kind == "table" and TABLE_RE.fullmatch(anchor_value):
        return rendered
    if kind in {"program", "field"}:
        match = PROGRAM_OR_FIELD_RE.fullmatch(anchor_value)
        if match:
            inferred_kind = "program" if match.group(1)[-1] in "tmpir" else "field"
            return rendered if kind == inferred_kind else None
    if kind == "env" and ENV_RE.fullmatch(anchor_value):
        return rendered
    if kind == "scope" and SCOPE_RE.fullmatch(anchor_value):
        return rendered
    if kind == "error" and ERROR_RE.fullmatch(anchor_value):
        return rendered
    if kind == "source" and SOURCE_FILE_RE.fullmatch(anchor_value):
        return rendered
    return None


def extract_safe_anchors(text: str) -> list[str]:
    """Extract typed workflow anchors without persisting arbitrary prompt text."""

    lowered = str(text).lower()
    anchors: set[str] = set()

    for term in SAFE_CJK_TERMS:
        if term in text:
            anchors.add(f"term:{term}")

    for phrase, name in SAFE_TOOLS.items():
        if phrase in lowered:
            anchors.add(f"tool:{name}")

    for match in TABLE_RE.findall(lowered):
        anchors.add(f"table:{match}")

    for match in PROGRAM_OR_FIELD_RE.finditer(lowered):
        letters, digits = match.groups()
        token = f"{letters}{digits}"
        kind = "program" if letters[-1] in "tmpir" else "field"
        anchors.add(f"{kind}:{token}")

    for match in ENV_RE.findall(lowered):
        anchors.add(f"env:{match}")

    for match in SCOPE_RE.findall(lowered):
        anchors.add(f"scope:{match}")

    for match in ERROR_RE.findall(lowered):
        anchors.add(f"error:{match}")

    for match in SOURCE_FILE_RE.findall(lowered):
        anchors.add(f"source:{match}")

    return sorted(anchor for anchor in anchors if _safe_anchor(anchor))


def shadow_query_projection(text: str, anchors: list[str] | None = None) -> str:
    """Project safe typed anchors into a compact bilingual routing query."""

    safe_anchors = [
        safe
        for item in (anchors if anchors is not None else extract_safe_anchors(text))
        if (safe := _safe_anchor(item)) is not None
    ]
    projected: list[str] = []
    for anchor in safe_anchors:
        kind, _, value = anchor.partition(":")
        if kind == "term":
            value = TERM_PROJECTIONS.get(value, value)
        elif kind == "tool":
            value = value.replace("-", " ").replace("_", " ")
        projected.append(value)
    if not projected:
        return "no-safe-routing-anchors"
    return " ".join(dict.fromkeys(projected))


def sanitize_candidates(
    candidates: list[dict[str, Any]],
    limit: int = 2,
    digest_value=digest,
) -> list[dict[str, Any]]:
    safe: list[dict[str, Any]] = []
    for candidate in candidates[: max(0, min(limit, 8))]:
        tier = str(candidate.get("tier") or candidate.get("decision_tier") or "searchable")
        if tier not in {"direct", "preload", "searchable", "suppress"}:
            tier = "searchable"
        relation = str(candidate.get("relation") or "")
        if not re.fullmatch(r"[a-z_]{0,40}", relation):
            relation = ""
        score = max(0.0, min(1.0, float(candidate.get("score", candidate.get("activation_score", 0.0)))))
        safe.append(
            {
                "edge_id": _safe_edge_id(
                    candidate.get("edge_id") or candidate.get("id"), digest_value
                ),
                "relation": relation,
                "score": round(score, 4),
                "tier": tier,
            }
        )
    return safe


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.expanduser().resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


class ShadowStore:
    def __init__(self, path: str | Path = DEFAULT_SHADOW_DB) -> None:
        self.path = Path(path).expanduser()
        if cloud_synced_path(self.path):
            raise ValueError("shadow_store_must_be_machine_local")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.key_path = Path(str(self.path) + ".key")
        self._key = load_or_create_key(self.key_path)
        self._lock = _lock_for(self.path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        """Initialize idempotent schema, tolerating brief cross-process WAL locks."""

        for attempt in range(_SCHEMA_INIT_ATTEMPTS):
            try:
                with self._lock, self._db() as db:
                    db.executescript(SCHEMA)
                    migrate_inline_feedback(db)
                return
            except sqlite3.OperationalError as exc:
                retryable = any(token in str(exc).lower() for token in ("locked", "busy"))
                if not retryable or attempt == _SCHEMA_INIT_ATTEMPTS - 1:
                    raise
                time.sleep(_SCHEMA_INIT_RETRY_SECONDS * (2**attempt))

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5.0)
        self._secure_permissions()
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _secure_permissions(self) -> None:
        for candidate in (
            self.path,
            Path(str(self.path) + "-wal"),
            Path(str(self.path) + "-shm"),
            self.key_path,
        ):
            try:
                os.chmod(candidate, 0o600)
            except FileNotFoundError:
                continue

    def _digest(self, value: str) -> str:
        return keyed_digest(self._key, value)

    @contextlib.contextmanager
    def _db(self):
        """Commit or roll back one transaction and always close the handle."""

        db = self._connect()
        try:
            with db:
                yield db
        finally:
            db.close()
            self._secure_permissions()

    def record_observation(
        self,
        *,
        profile: str,
        query: str,
        anchors: list[str],
        candidates: list[dict[str, Any]],
        session_id: str = "",
        task_id: str = "",
    ) -> dict[str, Any]:
        safe_profile = _profile(profile)
        safe_anchors = sorted(
            {safe for item in anchors if (safe := _safe_anchor(item)) is not None}
        )[:32]
        safe_candidates = sanitize_candidates(candidates, limit=2, digest_value=self._digest)
        event = {
            "event_id": str(uuid.uuid4()),
            "created_at": utc_now(),
            "profile": safe_profile,
            "machine_digest": self._digest(platform.node() or "unknown-machine")[:16],
            "session_digest": self._digest(str(session_id)) if session_id else "",
            "task_digest": self._digest(str(task_id)) if task_id else "",
            "query_digest": self._digest(str(query)),
            "anchors": safe_anchors,
            "candidates": safe_candidates,
        }
        with self._lock, self._db() as db:
            db.execute(
                """INSERT INTO shadow_events(
                    event_id,created_at,profile,machine_digest,session_digest,task_digest,
                    query_digest,anchors_json,candidates_json
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    event["event_id"],
                    event["created_at"],
                    event["profile"],
                    event["machine_digest"],
                    event["session_digest"],
                    event["task_digest"],
                    event["query_digest"],
                    json.dumps(safe_anchors, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(safe_candidates, separators=(",", ":")),
                ),
            )
        return event

    def record_feedback(
        self,
        event_id: str,
        profile: str,
        verdict: str,
        seconds_saved: float,
        used_edges: list[str],
    ) -> dict[str, Any]:
        safe_profile = _profile(profile)
        if verdict not in {"helpful", "neutral", "harmful"}:
            raise ValueError("verdict must be helpful, neutral, or harmful")
        seconds = max(0.0, min(86400.0, float(seconds_saved)))
        safe_used_edges = sorted({_safe_edge_id(edge, self._digest) for edge in used_edges})[:8]
        feedback_at = utc_now()
        with self._lock, self._db() as db:
            event = db.execute(
                "SELECT 1 FROM shadow_events WHERE event_id=? AND profile=?",
                (str(event_id), safe_profile),
            ).fetchone()
            if event is None:
                raise LookupError("shadow_event_not_found_for_profile")
            try:
                db.execute(
                    """INSERT INTO shadow_feedback(
                         event_id,profile,verdict,seconds_saved,used_edges_json,feedback_at
                       ) VALUES(?,?,?,?,?,?)""",
                    (
                        str(event_id),
                        safe_profile,
                        verdict,
                        seconds,
                        json.dumps(safe_used_edges, separators=(",", ":")),
                        feedback_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise LookupError("shadow_feedback_already_recorded") from exc
        return {
            "event_id": str(event_id),
            "profile": safe_profile,
            "verdict": verdict,
            "seconds_saved": seconds,
            "used_edges": safe_used_edges,
            "feedback_at": feedback_at,
        }

    def report(self, profile: str, days: int = 14) -> dict[str, Any]:
        safe_profile = _profile(profile)
        safe_days = max(1, min(int(days), 3650))
        cutoff = (dt.datetime.now(dt.UTC) - dt.timedelta(days=safe_days)).isoformat()
        with self._lock, self._db() as db:
            rows = db.execute(
                """SELECT e.event_id,e.created_at,e.profile,e.candidates_json,
                          f.verdict,f.seconds_saved,f.used_edges_json,f.feedback_at
                   FROM shadow_events AS e
                   LEFT JOIN shadow_feedback AS f
                     ON f.event_id=e.event_id AND f.profile=e.profile
                   WHERE e.profile=? AND e.created_at>=?
                   ORDER BY e.created_at""",
                (safe_profile, cutoff),
            ).fetchall()

        events = len(rows)
        candidate_events = sum(bool(json.loads(row["candidates_json"])) for row in rows)
        total_feedback_rows = [row for row in rows if row["verdict"]]
        feedback_rows = [
            row
            for row in total_feedback_rows
            if bool(json.loads(row["candidates_json"]))
        ]
        feedback_events = len(feedback_rows)
        helpful = sum(row["verdict"] == "helpful" for row in feedback_rows)
        harmful = sum(row["verdict"] == "harmful" for row in feedback_rows)
        helpful_seconds = [
            float(row["seconds_saved"] or 0.0)
            for row in feedback_rows
            if row["verdict"] == "helpful"
        ]
        coverage = candidate_events / events if events else 0.0
        feedback_coverage = feedback_events / candidate_events if candidate_events else 0.0
        helpful_precision = helpful / feedback_events if feedback_events else 0.0
        harmful_rate = harmful / feedback_events if feedback_events else 0.0
        median_seconds = statistics.median(helpful_seconds) if helpful_seconds else 0.0
        checks = {
            "minimum_events": events >= 100,
            "candidate_coverage": coverage >= 0.30,
            "feedback_coverage": feedback_coverage >= 0.70,
            "helpful_precision": helpful_precision >= 0.70,
            "harmful_rate": harmful_rate < 0.02,
            "median_seconds_saved": median_seconds >= 60.0,
        }
        return {
            "profile": safe_profile,
            "days": safe_days,
            "events": events,
            "candidate_events": candidate_events,
            "feedback_events": feedback_events,
            "total_feedback_events": len(total_feedback_rows),
            "coverage": round(coverage, 4),
            "feedback_coverage": round(feedback_coverage, 4),
            "helpful_precision": round(helpful_precision, 4),
            "harmful_rate": round(harmful_rate, 4),
            "median_seconds_saved": round(float(median_seconds), 2),
            "gate": {
                "eligible_for_influence_review": all(checks.values()),
                "checks": checks,
                "boundary": "Passing permits a human influence review only; it never enables injection automatically.",
            },
        }

    def maintenance(self, retention_days: int = 30, apply: bool = False) -> dict[str, Any]:
        """Preview or purge expired soft events; canonical graph data is out of scope."""

        safe_days = max(1, min(int(retention_days), 3650))
        cutoff = (dt.datetime.now(dt.UTC) - dt.timedelta(days=safe_days)).isoformat()
        with self._lock, self._db() as db:
            eligible = int(
                db.execute(
                    "SELECT COUNT(*) FROM shadow_events WHERE created_at<?", (cutoff,)
                ).fetchone()[0]
            )
            deleted = 0
            if apply and eligible:
                deleted = int(
                    db.execute(
                        "DELETE FROM shadow_events WHERE created_at<?", (cutoff,)
                    ).rowcount
                )
            remaining = int(db.execute("SELECT COUNT(*) FROM shadow_events").fetchone()[0])

        if apply and deleted:
            with self._lock, self._db() as db:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
                db.execute("VACUUM")

        return {
            "retention_days": safe_days,
            "cutoff": cutoff,
            "applied": bool(apply),
            "eligible_events": eligible,
            "deleted_events": deleted,
            "remaining_events": remaining,
            "canonical_edge_write": False,
            "boundary": "Maintenance only purges machine-local soft events and their feedback.",
        }
