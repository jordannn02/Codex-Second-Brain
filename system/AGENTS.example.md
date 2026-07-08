# Codex Second Brain OS - Agent Instructions

Use this as a public-safe starting point for an AI agent working with an Obsidian-style second brain.

## Startup Context

Before non-trivial work, load the smallest useful context layer:

1. `_CLAUDE.md` - local agent rules and safety boundaries.
2. `index.md` - navigation map.
3. `Home.md` - dashboard and current project entry points.
4. `CRITICAL_FACTS.md` - tiny always-load facts.

Do not read the entire vault before every task. Start narrow, then expand only when the task needs it.

## Capability Preflight

Classify the request before acting:

- quick answer;
- code or repo work;
- document conversion;
- data or SQL analysis;
- browser or app automation;
- GitHub workflow;
- vault search;
- memory graph routing;
- current external information;
- destructive or permission-sensitive action.

Choose the narrowest useful capability. If the task has a known memory graph route, prefer that route but still verify evidence.

## Delivery First

The user-visible result comes first.

```text
deliver answer / file / query result / report / artifact
  -> then capture durable memory
  -> then update graph edges
  -> then leave broad cleanup to consolidation
```

Do not make the user wait for memory capture before receiving the actual result.

## Evidence Boundary

Memory is not proof. Keep evidence layers separate:

- note or meeting context;
- documentation;
- source code;
- test result;
- SQL or data result;
- runtime screen;
- manual approval;
- external source.

State which layer supports the conclusion.

## Capture Routing

Save only durable signals:

- routes that worked;
- routes that failed;
- decisions;
- proof chains;
- reusable mappings;
- deliverables;
- contradictions.

Do not save trivial chat, secrets, raw private screenshots, private financial records, unverified guesses, or anything the user marked as not for saving.

## Memory Graph

When a route succeeds, strengthen it. When a route fails, weaken it or add an `avoid_if` / `suppress` edge. Keep evidence paths so future agents can audit why the route changed.

## Dry-Run-First Maintenance

Automation should report before it writes. Consolidation may identify stale notes, orphan candidates, low-confidence edges, and duplicate candidates, but deletion, archival, merging, or dense historical rewriting requires explicit permission.

## Public Safety

If this vault or system is published, publish only:

- methods;
- schemas;
- redacted examples;
- synthetic fixtures;
- safe docs.

Never publish real secrets, customer data, private notes, raw transcripts, production identifiers, or private vault exports.
