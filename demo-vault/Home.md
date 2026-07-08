---
date: 2026-07-08
type: dashboard
tags:
  - demo
  - dashboard
ai-first: true
---

# Demo Vault Home

## For future Claude

This demo vault is synthetic and public-safe. Start here, then use [[index]] to navigate examples, fixtures, and logs.

## Start Here

- [[index]] - Navigation map.
- [[_CLAUDE]] - Demo operating rules.
- [[CRITICAL_FACTS]] - Tiny always-load context.

## Example Workflows

- [[Knowledge/Examples/2026-07-08 - Repeated Debugging Route Learning]]
- [[Knowledge/Examples/2026-07-08 - Tool Overload Auto Router]]
- [[Knowledge/Examples/2026-07-08 - Meeting to Execution Memory]]

## Golden Fixtures

- `fixtures/memory-graph.jsonl`
- `fixtures/capture-events.jsonl`
- `fixtures/momo-route-result.json`

## Validation

```bash
python3 -m codex_second_brain.cli validate demo-vault
python3 -m codex_second_brain.cli consolidate demo-vault --dry-run
```
