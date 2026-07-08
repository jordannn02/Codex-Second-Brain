# System Package

This folder contains the public-safe operating layer of the second brain project.

It is meant to be copied, adapted, and trimmed. It is not a dump of a private vault.

## Components

| File | Purpose |
|---|---|
| `AGENTS.example.md` | Minimal agent operating manual for capability routing, delivery-first behavior, and safe capture. |
| `capture-routing.md` | Rules for deciding what gets saved after a task. |
| `memory-graph.md` | Lightweight model for turning repeated workflow attempts into reusable routing edges. |
| `weekly-consolidation.md` | Maintenance loop for indexes, stale captures, and evidence preservation. |
| `.codex/commands/README.md` | Public command catalog pattern without private command bodies. |

## Design Principle

The system layer should answer:

1. What context should the agent load before acting?
2. How should the agent choose tools?
3. What must be delivered to the user first?
4. What evidence is strong enough for the claim?
5. What should be saved for next time?
6. What must never be published?

## Recommended Adoption Order

1. Add `AGENTS.example.md` rules to your agent environment.
2. Create a tiny `_CLAUDE.md`, `index.md`, `Home.md`, and `CRITICAL_FACTS.md` in your vault.
3. Use `capture-routing.md` manually for a week.
4. Add memory graph only after you can name repeated workflow wins and failures.
5. Add weekly consolidation once append-only captures start to accumulate.

## Safety Boundary

Keep this folder public-safe. Do not add credentials, raw transcripts, customer names, production document numbers, private screenshots, or company-specific internal logic.

