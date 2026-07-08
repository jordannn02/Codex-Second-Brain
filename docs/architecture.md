# Architecture

Codex Second Brain OS separates fast retrieval from durable evidence. The goal is not infinite memory. The goal is to help future agents know what to read, which route to try, what proof is required, and which path should be avoided.

## Layers

```text
user task
  -> startup context
  -> capability preflight
  -> bounded execution
  -> evidence verification
  -> capture event
  -> memory graph update
  -> weekly consolidation
```

## Startup Context

The agent should load only a small navigation layer first:

- `_CLAUDE.md` for local operating rules;
- `index.md` for the vault map;
- `Home.md` for the human-facing dashboard;
- `CRITICAL_FACTS.md` for tiny always-load facts.

This prevents the agent from reading the entire vault before every task.

## Capture Events

A capture event is a small durable signal produced after user-visible delivery. It can describe a route that worked, a route that failed, a decision, a proof chain, or a contradiction.

Capture events are stored as JSONL so they can be reviewed, filtered, tested, and later promoted into memory graph edges.

## Memory Graph

The memory graph is an inspectable route-learning layer. It stores edges such as:

- `preferred_tool_for`;
- `workflow_shortcut`;
- `evidence_chain`;
- `verified_by`;
- `avoid_if`;
- `suppress`.

Successful routes gain weight. Failed routes gain failure signatures and may be weakened or suppressed. Evidence is preserved; bad paths simply become less attractive.

## Dry-Run Consolidation

Consolidation should be report-first:

1. Refresh indexes.
2. Detect stale or orphaned items.
3. Review low-confidence graph edges.
4. Identify duplicates or cleanup candidates.
5. Ask for permission before deletion, archival, merging, or dense historical rewrites.

The public reference CLI deliberately implements consolidation as a dry-run report.

## Evidence Boundary

Memory is not proof. Notes can guide the agent, but claims still need the right evidence layer:

- source files;
- tests;
- SQL or data results;
- runtime checks;
- screenshots;
- manual approval;
- external source citations when applicable.

The memory graph can suggest a route. It cannot authorize unsafe action or skip verification.
