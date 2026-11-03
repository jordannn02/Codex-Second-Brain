#!/usr/bin/env python3
"""Local Qwen3 semantic search for CodexSecondBrain.

Lexical and semantic results remain separate. The semantic index is stored
outside the vault and contains vectors plus path/offset metadata, never note
text. If the model or index is unavailable, search fails open to lexical hits.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# Read-only search must not create __pycache__ in a vault.
sys.dont_write_bytecode = True


DEFAULT_VAULT = Path(".")
DEFAULT_HOME = Path("~/.local/share/codex-second-brain/qwen3-search").expanduser()
MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
MODEL_WEIGHT = "model.safetensors"
MODEL_SHA256 = "0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd"
INDEX_SCHEMA = "codex-second-brain-qwen3-index/v1"
RESULT_SCHEMA = "codex-second-brain-search/v1"
CHUNK_CHARS = 2400
CHUNK_OVERLAP = 240
MAX_SEQ_LENGTH = 4096
BATCH_SIZE = 8
SCOPE_RE = re.compile(r"^[A-Za-z0-9_-]+$")
INTENT_HINT_RE = re.compile(
    r"(?:怎麼|如何|為什麼|為何|差異|影響|用途|流程|驗證|說明|找出|教我|"
    r"\b(?:how|why|what|difference|impact|explain|verify|process)\b)",
    re.IGNORECASE,
)
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*|\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?")
LEXICAL_CONFIDENT_SCORE = 20.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=DEFAULT_VAULT, help="Vault root")
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME, help="Local runtime root")
    parser.add_argument("--scope", default="core", help="Vault scope profile")
    parser.add_argument("--backend", choices=("lexical", "qwen3"), default="lexical",
                        help="Semantic backend; lexical is dependency-free and the default")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check the local installation")
    doctor.add_argument("--verify-model", action="store_true", help="Hash the model weight")
    doctor.add_argument("--json", action="store_true")

    index = subparsers.add_parser("index", help="Build or refresh the semantic index")
    index.add_argument("--force", action="store_true")
    index.add_argument("--apply", action="store_true", help="Explicitly authorize local index persistence")
    index.add_argument("--json", action="store_true")

    search = subparsers.add_parser("search", help="Return lexical and semantic lanes")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=5)
    search.add_argument("--no-rebuild", action="store_true")
    search.add_argument(
        "--semantic-mode",
        choices=("auto", "always", "never"),
        default="auto",
        help="Auto-route semantic search after lexical retrieval (default: auto)",
    )
    search.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def normalized_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    vault = args.path.expanduser().resolve()
    home = args.home.expanduser().resolve()
    if not SCOPE_RE.fullmatch(args.scope):
        raise ValueError("scope may contain only letters, digits, underscore, and hyphen")
    return vault, home


def load_runner(vault: Path):
    script_dir = vault / ".codex" / "scripts"
    script_path = script_dir / "retrieval_benchmark.py"
    if not script_path.is_file():
        raise FileNotFoundError(f"lexical runner not found: {script_path}")
    sys.path.insert(0, str(script_dir))
    spec = importlib.util.spec_from_file_location("vault_retrieval_benchmark", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import lexical runner: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def title_for(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return Path(fallback).stem


def windows_with_offsets(value: str, size: int, overlap: int) -> Iterator[tuple[int, int, str]]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("chunk size must be positive and overlap must be smaller")
    step = size - overlap
    for start in range(0, max(len(value), 1), step):
        body = value[start : start + size]
        if not body and value:
            continue
        yield start, start + len(body), body
        if start + size >= len(value):
            break


def make_chunks(notes: list[dict[str, str]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for note in notes:
        title = title_for(note["content"], note["path"])
        prefix = f"Path: {note['path']}\nTitle: {title}\n"
        for chunk_index, (start, end, body) in enumerate(
            windows_with_offsets(note["content"], CHUNK_CHARS, CHUNK_OVERLAP),
            start=1,
        ):
            chunks.append(
                {
                    "path": note["path"],
                    "chunk_index": chunk_index,
                    "start": start,
                    "end": end,
                    "text": f"{prefix}Chunk: {chunk_index}\n{body}",
                }
            )
    return chunks


def metadata_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = ("path", "chunk_index", "start", "end")
    return [{key: chunk[key] for key in keys} for chunk in chunks]


def index_paths(home: Path, scope: str) -> tuple[Path, Path, Path]:
    root = home / "indexes" / scope
    return root, root / "metadata.json", root / "vectors.npy"


def model_path(home: Path) -> Path:
    return home / "models" / "Qwen3-Embedding-0.6B"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def model_available(home: Path) -> tuple[bool, str | None]:
    root = model_path(home)
    required = (
        root / MODEL_WEIGHT,
        root / "config.json",
        root / "config_sentence_transformers.json",
        root / "modules.json",
        root / "tokenizer.json",
    )
    missing = [str(path) for path in required if not path.is_file()]
    return (not missing, None if not missing else f"missing model files: {', '.join(missing)}")


def load_model(home: Path):
    import torch
    from sentence_transformers import SentenceTransformer

    available, reason = model_available(home)
    if not available:
        raise FileNotFoundError(reason)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = SentenceTransformer(str(model_path(home)), device=device, local_files_only=True)
    model.max_seq_length = MAX_SEQ_LENGTH
    return model, device


@contextmanager
def index_lock(home: Path, scope: str) -> Iterator[None]:
    root, _, _ = index_paths(home, scope)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = root / ".index.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        os.chmod(lock_path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_metadata(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def index_is_current(metadata: dict[str, Any] | None, corpus_sha: str) -> bool:
    if not metadata:
        return False
    return (
        metadata.get("schema") == INDEX_SCHEMA
        and metadata.get("corpus_sha256") == corpus_sha
        and metadata.get("model", {}).get("sha256") == MODEL_SHA256
        and metadata.get("chunking", {}).get("chars") == CHUNK_CHARS
        and metadata.get("chunking", {}).get("overlap") == CHUNK_OVERLAP
        and metadata.get("max_seq_length") == MAX_SEQ_LENGTH
    )


def write_index(home: Path, scope: str, vectors: Any, metadata: dict[str, Any]) -> None:
    import numpy as np

    root, metadata_path, vectors_path = index_paths(home, scope)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    vector_temp = root / f".vectors.{os.getpid()}.tmp"
    metadata_temp = root / f".metadata.{os.getpid()}.tmp"
    try:
        with vector_temp.open("wb") as handle:
            np.save(handle, np.asarray(vectors, dtype=np.float32), allow_pickle=False)
        metadata_temp.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(vector_temp, 0o600)
        os.chmod(metadata_temp, 0o600)
        os.replace(vector_temp, vectors_path)
        os.replace(metadata_temp, metadata_path)
    finally:
        vector_temp.unlink(missing_ok=True)
        metadata_temp.unlink(missing_ok=True)


def build_index(
    home: Path,
    vault: Path,
    scope: str,
    runner: Any,
    notes: list[dict[str, str]] | None = None,
    model: Any | None = None,
    device: str | None = None,
) -> tuple[dict[str, Any], Any, str]:
    notes = notes if notes is not None else runner.load_corpus(vault, scope)
    corpus_sha = runner.corpus_sha256(notes)
    chunks = make_chunks(notes)
    if model is None or device is None:
        model, device = load_model(home)
    started = time.perf_counter()
    vectors = model.encode(
        [chunk["text"] for chunk in chunks],
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    metadata = {
        "schema": INDEX_SCHEMA,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "vault": str(vault),
        "scope": scope,
        "corpus_sha256": corpus_sha,
        "notes": len(notes),
        "chunks": metadata_chunks(chunks),
        "chunking": {"chars": CHUNK_CHARS, "overlap": CHUNK_OVERLAP},
        "max_seq_length": MAX_SEQ_LENGTH,
        "embedding_dimension": int(vectors.shape[1]),
        "model": {
            "name": MODEL_NAME,
            "revision": MODEL_REVISION,
            "sha256": MODEL_SHA256,
            "device": device,
        },
        "index_seconds": round(time.perf_counter() - started, 3),
        "privacy": "Vectors and path/offset metadata only; no note text is stored.",
    }
    with index_lock(home, scope):
        write_index(home, scope, vectors, metadata)
    return metadata, model, device


def load_vectors(home: Path, scope: str, metadata: dict[str, Any]):
    import numpy as np

    _, _, vectors_path = index_paths(home, scope)
    if not vectors_path.is_file():
        raise FileNotFoundError(f"semantic vectors not found: {vectors_path}")
    vectors = np.load(vectors_path, mmap_mode="r", allow_pickle=False)
    if vectors.ndim != 2 or vectors.shape[0] != len(metadata.get("chunks", [])):
        raise ValueError("semantic index shape does not match metadata")
    return vectors


def collapse_semantic_hits(scores: Any, chunks: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    best: dict[str, tuple[float, dict[str, Any]]] = {}
    for raw_score, chunk in zip(scores.tolist(), chunks, strict=True):
        score = float(raw_score)
        path = str(chunk["path"])
        if path not in best or score > best[path][0]:
            best[path] = (score, chunk)
    ranked = sorted(best.items(), key=lambda item: (-item[1][0], item[0]))[:top_k]
    return [
        {
            "path": path,
            "score": round(score, 6),
            "chunk_index": int(chunk["chunk_index"]),
            "start": int(chunk["start"]),
            "end": int(chunk["end"]),
        }
        for path, (score, chunk) in ranked
    ]


def _has_exact_identifier(query: str) -> bool:
    """Recognize query tokens that are usually safer on lexical search alone."""
    for token in TOKEN_RE.findall(query):
        if re.fullmatch(r"\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?", token):
            return True
        if any(char.isdigit() for char in token) and any(char.isalpha() for char in token):
            return True
        if "_" in token and len(token) >= 5:
            return True
        if token.isupper() and len(token) >= 3:
            return True
    return False


def semantic_route(
    query: str,
    lexical_hits: list[dict[str, Any]],
    mode: str = "auto",
) -> tuple[bool, str]:
    """Return whether semantic search is needed after the lexical first pass."""
    if mode == "always":
        return True, "forced"
    if mode == "never":
        return False, "disabled"
    if not lexical_hits:
        return True, "lexical-empty"

    normalized = " ".join(query.split())
    token_count = len(normalized.split())
    chinese_char_count = len(re.findall(r"[\u3400-\u9fff]", normalized))
    has_intent = bool(INTENT_HINT_RE.search(normalized))
    has_identifier = _has_exact_identifier(normalized)
    try:
        top_score = float(lexical_hits[0].get("score", 0.0))
    except (TypeError, ValueError):
        top_score = 0.0

    # Natural-language intent wins over an identifier embedded in the question.
    if has_intent and (chinese_char_count >= 4 or token_count >= 3):
        return True, "natural-language-intent"
    if not has_identifier and (chinese_char_count >= 8 or token_count >= 4):
        return True, "natural-language-query"
    if has_identifier and token_count <= 5 and top_score >= LEXICAL_CONFIDENT_SCORE:
        return False, "exact-identifier"
    if top_score < LEXICAL_CONFIDENT_SCORE:
        return True, "weak-lexical-match"
    return False, "lexical-confident"


def search_payload(
    vault: Path,
    home: Path,
    scope: str,
    query: str,
    top_k: int,
    allow_rebuild: bool,
    runner: Any | None = None,
    semantic_mode: str = "auto",
    backend: str = "lexical",
) -> dict[str, Any]:
    if top_k <= 0:
        raise ValueError("top-k must be positive")
    runner = runner or load_runner(vault)
    notes = runner.load_corpus(vault, scope)
    corpus_sha = runner.corpus_sha256(notes)
    lexical_hits = runner.rank(notes, query)[:top_k]
    payload: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "query": query,
        "vault": str(vault),
        "scope": scope,
        "corpus_sha256": corpus_sha,
        "routing": "lexical-primary-and-semantic-supplement-kept-separate",
        "lexical": {"status": "ok", "hits": lexical_hits},
        "semantic": {"status": "unavailable", "hits": []},
        "routing_decision": {
            "mode": semantic_mode,
            "semantic_called": False,
            "reason": None,
        },
        "privacy": "Read-only vault access; no cloud API call.",
    }
    should_search_semantic, route_reason = semantic_route(query, lexical_hits, semantic_mode)
    if backend == "lexical":
        should_search_semantic, route_reason = False, "lexical-backend-selected"
    payload["routing_decision"] = {
        "mode": semantic_mode,
        "semantic_called": False,
        "reason": route_reason,
    }
    if not should_search_semantic:
        payload["semantic"] = {
            "status": "skipped",
            "reason": route_reason,
            "hits": [],
        }
        return payload
    try:
        available, reason = model_available(home)
        if not available:
            raise FileNotFoundError(reason)
        _, metadata_path, _ = index_paths(home, scope)
        metadata = read_metadata(metadata_path)
        model = None
        device = None
        rebuilt = False
        if not index_is_current(metadata, corpus_sha):
            if not allow_rebuild:
                raise RuntimeError("semantic index is missing or stale; run the index command")
            metadata, model, device = build_index(home, vault, scope, runner, notes=notes)
            rebuilt = True
        if metadata is None:
            raise RuntimeError("semantic index metadata is unavailable")
        vectors = load_vectors(home, scope, metadata)
        if model is None or device is None:
            model, device = load_model(home)
        started = time.perf_counter()
        payload["routing_decision"]["semantic_called"] = True
        query_vector = model.encode(
            [query],
            prompt_name="query",
            batch_size=1,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0]
        scores = vectors @ query_vector
        payload["semantic"] = {
            "status": "ok",
            "model": MODEL_NAME,
            "device": device,
            "index_built_at": metadata["built_at"],
            "index_rebuilt": rebuilt,
            "query_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "hits": collapse_semantic_hits(scores, metadata["chunks"], top_k),
        }
    except Exception as exc:  # lexical results intentionally survive semantic failure
        payload["semantic"] = {
            "status": "unavailable",
            "reason": f"{type(exc).__name__}: {exc}",
            "hits": [],
        }
    return payload


def doctor_payload(vault: Path, home: Path, scope: str, verify_model: bool) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    checks["home_exists"] = home.is_dir()
    checks["home_mode_700"] = home.is_dir() and (home.stat().st_mode & 0o777) == 0o700
    checks["runtime_python"] = (home / "venv" / "bin" / "python").is_file()
    checks["lexical_runner"] = (vault / ".codex" / "scripts" / "retrieval_benchmark.py").is_file()
    available, reason = model_available(home)
    checks["model_files"] = available
    checks["model_files_reason"] = reason
    try:
        import numpy
        import sentence_transformers
        import torch

        checks["dependencies"] = True
        versions = {
            "numpy": numpy.__version__,
            "sentence_transformers": sentence_transformers.__version__,
            "torch": torch.__version__,
        }
        device = "mps" if torch.backends.mps.is_available() else "cpu"
    except Exception as exc:
        checks["dependencies"] = False
        checks["dependencies_reason"] = f"{type(exc).__name__}: {exc}"
        versions = {}
        device = None
    if verify_model and available:
        observed_sha = sha256_file(model_path(home) / MODEL_WEIGHT)
        checks["model_sha256"] = observed_sha == MODEL_SHA256
    elif verify_model:
        checks["model_sha256"] = False
    _, metadata_path, vectors_path = index_paths(home, scope)
    checks["index_metadata"] = metadata_path.is_file()
    checks["index_vectors"] = vectors_path.is_file()
    required_checks = (
        "home_exists",
        "home_mode_700",
        "runtime_python",
        "lexical_runner",
        "model_files",
        "dependencies",
    )
    if verify_model:
        required_checks += ("model_sha256",)
    return {
        "schema": "codex-second-brain-qwen3-doctor/v1",
        "ok": all(bool(checks[name]) for name in required_checks),
        "home": str(home),
        "vault": str(vault),
        "model": {"name": MODEL_NAME, "revision": MODEL_REVISION, "device": device},
        "versions": versions,
        "checks": checks,
    }


def print_search(payload: dict[str, Any]) -> None:
    print("Lexical")
    for index, hit in enumerate(payload["lexical"]["hits"], start=1):
        print(f"{index}. {hit['path']}  score={hit['score']}")
    print("\nSemantic")
    semantic = payload["semantic"]
    if semantic["status"] != "ok":
        print(f"{semantic['status']}: {semantic.get('reason', 'unknown reason')}")
        return
    for index, hit in enumerate(semantic["hits"], start=1):
        print(
            f"{index}. {hit['path']}  score={hit['score']}  "
            f"chunk={hit['chunk_index']} offsets={hit['start']}:{hit['end']}"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault, home = normalized_paths(args)
    # Never re-exec, install dependencies, download a model or rebuild an index on search.
    if args.command == "doctor":
        payload = doctor_payload(vault, home, args.scope, args.verify_model)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("Qwen3 semantic search: OK" if payload["ok"] else "Qwen3 semantic search: FAILED")
        return 0 if payload["ok"] else 1
    runner = load_runner(vault)
    if args.command == "index":
        if args.backend != "qwen3" or not args.apply:
            print(json.dumps({"ok": False, "error": "index requires --backend qwen3 and --apply; no files written"}))
            return 2
        notes = runner.load_corpus(vault, args.scope)
        corpus_sha = runner.corpus_sha256(notes)
        _, metadata_path, _ = index_paths(home, args.scope)
        current = read_metadata(metadata_path)
        if not args.force and index_is_current(current, corpus_sha):
            payload = {"status": "current", "metadata": current}
        else:
            metadata, _, _ = build_index(home, vault, args.scope, runner, notes=notes)
            payload = {"status": "rebuilt", "metadata": metadata}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                f"Semantic index {payload['status']}: "
                f"{payload['metadata']['notes']} notes, "
                f"{len(payload['metadata']['chunks'])} chunks"
            )
        return 0
    if args.command == "search":
        payload = search_payload(
            vault,
            home,
            args.scope,
            args.query,
            args.top_k,
            allow_rebuild=False,
            runner=runner,
            semantic_mode=args.semantic_mode,
            backend=args.backend,
        )
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_search(payload)
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
