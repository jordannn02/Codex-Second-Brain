---
date: 2026-07-08
type: dev-log
tags:
  - demo
  - adaptive-routing
  - memory-graph
ai-first: true
source: "Synthetic public demo fixture."
---

# Demo Adaptive Routing Cases

## For future Claude

This dev log demonstrates delivery-first behavior across three examples: debugging route learning, tool overload auto-routing, and meeting-to-execution memory. It is synthetic and public-safe.

## Work Completed

- Added route-learning examples under `Knowledge/Examples/`.
- Added JSONL memory graph and capture-event fixtures.
- Added a synthetic `momo-tools` route result.
- Added dry-run validation and consolidation examples.

## Verification

Run from the repository root:

```bash
python3 -m codex_second_brain.cli validate demo-vault
python3 -m codex_second_brain.cli consolidate demo-vault --dry-run
python3 -m codex_second_brain.cli route-suggest demo-vault "debugging noisy search source trace"
```

## Boundary

No real customer data, production IDs, credentials, screenshots, or private meeting content are included.
