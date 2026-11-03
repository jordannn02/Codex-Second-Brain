#!/usr/bin/env python3
"""Verify one capability/version contract across local, installed, and public surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path


SCHEMA = "second-brain-capability-audit/v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def actual_version(root: Path, source: str) -> str:
    path = root / source
    if path.name == "pyproject.toml":
        return str(tomllib.loads(path.read_text(encoding="utf-8"))["project"]["version"])
    return path.read_text(encoding="utf-8").strip()


def audit(contract_path: Path, roots: dict[str, Path]) -> dict[str, object]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    canonical_sha = sha256(contract_path)
    blockers: list[str] = []
    surfaces: dict[str, dict[str, object]] = {}
    for surface, root in roots.items():
        definition = contract["surfaces"][surface]
        replica = root / definition["contract_path"]
        contract_match = replica.is_file() and sha256(replica) == canonical_sha
        if not contract_match:
            blockers.append(f"contract_mismatch:{surface}")
        try:
            version = actual_version(root, str(definition["version_source"]))
        except (OSError, KeyError, tomllib.TOMLDecodeError):
            version = None
        version_match = version == definition["version"]
        if not version_match:
            blockers.append(f"version_mismatch:{surface}")
        surfaces[surface] = {
            "root": str(root),
            "contract": str(replica),
            "contract_match": contract_match,
            "declared_version": definition["version"],
            "actual_version": version,
            "version_match": version_match,
        }

    capability_states: dict[str, dict[str, str]] = {}
    allowed_states = {"verified-working", "visible", "reference-only", "not-shipped"}
    for capability, matrix in contract["capabilities"].items():
        capability_states[capability] = {}
        for surface, root in roots.items():
            claim = matrix[surface]
            state = str(claim["state"])
            capability_states[capability][surface] = state
            if state not in allowed_states:
                blockers.append(f"unknown_state:{capability}:{surface}")
                continue
            artifact = claim.get("artifact")
            if state == "not-shipped":
                if artifact:
                    blockers.append(f"not_shipped_has_artifact_claim:{capability}:{surface}")
                continue
            if not isinstance(artifact, str) or not (root / artifact).is_file():
                blockers.append(f"claimed_artifact_missing:{capability}:{surface}")

    blockers = sorted(set(blockers))
    return {
        "schema": SCHEMA,
        "contract_version": contract.get("contract_version"),
        "contract_sha256": canonical_sha,
        "level": "verified-working" if not blockers else "blocked",
        "blockers": blockers,
        "surfaces": surfaces,
        "capability_states": capability_states,
        "rule": "Consumers may route only to capabilities claimed by the active surface; visible/reference-only never implies vault-local parity.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--installed-skill", required=True)
    parser.add_argument("--public-package", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        payload = audit(
            Path(args.contract).expanduser().resolve(),
            {
                "vault-local": Path(args.vault).expanduser().resolve(),
                "installed-skill": Path(args.installed_skill).expanduser().resolve(),
                "public-package": Path(args.public_package).expanduser().resolve(),
            },
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload["level"])
        return 0 if not payload["blockers"] else 1
    except (OSError, KeyError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        print(json.dumps({"schema": SCHEMA, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
