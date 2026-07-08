# System Package

This folder contains the public-safe operating layer for Codex Second Brain OS. It is designed for agents that need to improve their routing behavior over time instead of merely storing notes.

## Components

| File | Purpose |
|---|---|
| `AGENTS.example.md` | Minimal agent operating manual: startup context, delivery-first behavior, adaptive routing, and safety boundaries. |
| `capture-routing.md` | Rules for deciding what becomes durable memory after delivery. |
| `memory-graph.md` | Route memory model: reinforcement, weakening, suppression, evidence chains, and correction loops. |
| `weekly-consolidation.md` | Dry-run-first maintenance loop for stale captures, indexes, graph decay, and cleanup review. |
| `.codex/commands/README.md` | Public command catalog pattern without private command bodies. |

Related implementation files live outside this folder:

- `schemas/` contains machine-readable data contracts.
- `codex_second_brain/cli.py` contains the minimal reference CLI.
- `demo-vault/fixtures/` contains public-safe golden fixtures.
- `tests/` validates the demo vault and CLI behavior.

## System Responsibilities

For every non-trivial task, the system layer should answer six questions:

1. What startup context should the agent load before acting?
2. Which capability should the agent use first?
3. What must be delivered before memory work begins?
4. What evidence is required before the claim is trusted?
5. Which route should be strengthened, weakened, or suppressed?
6. What must never be saved or published?

## Adoption Order

1. Start with `AGENTS.example.md`.
2. Add `_CLAUDE.md`, `index.md`, `Home.md`, and `CRITICAL_FACTS.md` to your own vault.
3. Run `second-brain validate <vault>`.
4. Use `capture-routing.md` manually until the save boundary feels reliable.
5. Add JSONL capture events and memory graph edges.
6. Run `second-brain consolidate <vault> --dry-run` before any maintenance write.
7. Add scheduled consolidation only after dry-run reports are useful.

## Safety Boundary

Keep this folder public-safe. Do not add credentials, raw transcripts, customer names, production document numbers, private screenshots, company-specific procedures, or real private vault exports.
