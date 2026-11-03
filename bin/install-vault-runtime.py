#!/usr/bin/env python3
"""Install the public portable runtime into a vault; dry-run unless --apply."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNTIME = REPO / "system" / "vault-runtime"
ALLOWED_SUFFIXES = {".py", ".md", ".json", ".jsonl", ".template"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for group in ("commands", "references", "scripts", "fixtures", "memory_graph"):
        root = RUNTIME / group
        if not root.is_dir() and group == "fixtures":
            continue
        if not root.is_dir():
            raise ValueError(f"missing public runtime directory: {group}; install from a repository checkout")
        for source in sorted(root.rglob("*")):
            if "__pycache__" in source.parts or source.suffix not in ALLOWED_SUFFIXES:
                continue
            if source.is_symlink():
                raise ValueError(f"source symlink is not installable: {source.relative_to(RUNTIME)}")
            if not source.is_file():
                continue
            relative = source.relative_to(root)
            destination = Path("Knowledge/Codex/memory_graph") / relative if group == "memory_graph" else Path(".codex") / group / relative
            files[destination.as_posix()] = source.read_bytes()
    for name in ("THIRD_PARTY.md", "LICENSE.upstream"):
        source = RUNTIME / name
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"missing attribution file: {name}")
        files[f".codex/{name}"] = source.read_bytes()
    routing = (RUNTIME / "AGENTS.template.md").read_bytes()
    files[".codex/AGENTS.runtime.md"] = routing
    files["AGENTS.md"] = routing
    # An empty graph is valid; never ship private sidecars or touch an existing graph.
    files["Knowledge/Codex/memory_graph_edges.jsonl"] = b""
    return files


def checked_target(vault: Path, relative: str) -> Path:
    target = vault / relative
    current = vault
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"destination symlink refused: {relative}")
    if not target.resolve().is_relative_to(vault):
        raise ValueError(f"destination escapes vault: {relative}")
    return target


def plan(vault: Path, files: dict[str, bytes]) -> list[dict[str, str]]:
    changes = []
    for relative, content in files.items():
        target = checked_target(vault, relative)
        if target.exists():
            if not target.is_file():
                state = "conflict"
            elif relative in {"AGENTS.md", "Knowledge/Codex/memory_graph_edges.jsonl"}:
                state = "preserved"
            else:
                state = "unchanged" if target.read_bytes() == content else "conflict"
        else:
            state = "create"
        changes.append({"target": relative, "state": state, "sha256": digest(content)})
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vault", type=Path, help="new or existing vault directory")
    parser.add_argument("--apply", action="store_true", help="explicitly install missing files; never overwrite existing differences")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 12):
        print(json.dumps({"ok": False, "error": "portable runtime requires Python >=3.12"}))
        return 2
    try:
        if args.vault.expanduser().is_symlink():
            raise ValueError("vault root symlink refused")
        vault = args.vault.expanduser().resolve()
        if vault.exists() and not vault.is_dir():
            raise ValueError("vault must be a directory")
        files = source_files()
        changes = plan(vault, files)
        conflicts = [item["target"] for item in changes if item["state"] == "conflict"]
        report = {"ok": not conflicts, "mode": "apply" if args.apply else "dry-run", "vault": str(vault),
                  "changes": changes, "conflicts": conflicts, "written": [],
                  "dependencies": {"python": ">=3.12", "schema_and_export": "PyYAML (optional, required by those helpers)",
                                   "semantic": "optional: numpy, torch, sentence-transformers; existing local Qwen3 weights/index"},
                  "boundary": "No private notes, credentials, models, cloud settings or schedules are installed. A missing AGENTS.md receives public routing; existing AGENTS.md is preserved. Include .codex/AGENTS.runtime.md in existing routing manually after review. Other startup notes are separate: use second-brain init only as authorized."}
        if conflicts:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1
        if args.apply:
            for change in changes:
                if change["state"] != "create":
                    continue
                target = checked_target(vault, change["target"])
                target.parent.mkdir(parents=True, exist_ok=True)
                # Recheck after directory creation; x mode refuses concurrent replacement.
                target = checked_target(vault, change["target"])
                with target.open("xb") as stream:
                    stream.write(files[change["target"]])
                if digest(target.read_bytes()) != change["sha256"]:
                    raise OSError(f"readback mismatch: {change['target']}")
                report["written"].append(change["target"])
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}", "mode": "apply" if args.apply else "dry-run"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
