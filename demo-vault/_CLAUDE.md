---
date: 2026-07-08
type: operating-manual
tags:
  - demo
  - agent-rules
ai-first: true
---

# Demo Vault Operating Manual

## For future Claude

This is a synthetic public demo vault. Use it to show startup context, delivery-first capture, route memory, dry-run consolidation, and public-safe fixtures.

## Startup Context

Read these files before non-trivial work:

1. `_CLAUDE.md`
2. `index.md`
3. `Home.md`
4. `CRITICAL_FACTS.md`

## Delivery First

Deliver the user-visible result before saving memory.

## Capture Rules

Capture only durable signals:

- route worked;
- route failed;
- decision made;
- proof chain assembled;
- contradiction detected;
- deliverable created.

## Dry-Run Maintenance

Use dry-run reports before writing maintenance changes:

```bash
python3 -m codex_second_brain.cli consolidate demo-vault --dry-run
```

## Redaction Boundary

Do not add real client data, production IDs, private screenshots, credentials, transcripts, financial notes, or internal company procedures to this demo vault.
