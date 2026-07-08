# Demo Vault

This is a redacted, synthetic Obsidian-style vault. It demonstrates how Codex Second Brain OS turns work into durable route memory without exposing private data.

## Scenarios

1. A debugging workflow learns from a failed broad search route.
2. A tool-overload task uses adaptive capability routing.
3. A meeting-to-execution workflow captures decisions without saving raw transcripts.
4. A synthetic `momo-tools` route result becomes a capture event and candidate memory graph edge.

## Files

| File | Purpose |
|---|---|
| `_CLAUDE.md` | Demo vault operating rules. |
| `index.md` | Navigation map for future agents. |
| `Home.md` | Simple dashboard. |
| `CRITICAL_FACTS.md` | Tiny always-load context. |
| `Knowledge/Examples/2026-07-08 - Repeated Debugging Route Learning.md` | Debugging route reinforcement example. |
| `Knowledge/Examples/2026-07-08 - Tool Overload Auto Router.md` | Capability routing example. |
| `Knowledge/Examples/2026-07-08 - Meeting to Execution Memory.md` | Meeting capture and consolidation example. |
| `fixtures/memory-graph.jsonl` | Golden memory graph edges. |
| `fixtures/capture-events.jsonl` | Golden capture events. |
| `fixtures/momo-route-result.json` | Synthetic momo-tools route result. |
| `Dev Logs/2026-07-08 - Demo Adaptive Routing Cases.md` | Example implementation log. |
| `Logs/2026-07-08.md` | Operation log. |

## Validate

From the repository root:

```bash
python3 -m codex_second_brain.cli validate demo-vault
python3 -m codex_second_brain.cli consolidate demo-vault --dry-run
```

## Redaction Rule

Everything here is synthetic. Replace examples with your own public-safe fixtures before publishing.
