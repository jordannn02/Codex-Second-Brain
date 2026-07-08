# System Package

This folder contains the public-safe operating layer of Codex Second Brain OS.

It is designed for agents that need to improve their own routing behavior over time, not merely store notes.

## Components

| File | Purpose |
|---|---|
| `AGENTS.example.md` | Minimal agent operating manual for startup context, delivery-first behavior, adaptive routing, and safety boundaries. |
| `capture-routing.md` | Rules for deciding what gets saved after a task and what must remain unsaved. |
| `memory-graph.md` | Self-improving route memory: reinforcement, weakening, suppression, evidence chains, and correction loops. |
| `weekly-consolidation.md` | Automated maintenance loop for stale captures, indexes, graph decay, and cleanup review. |
| `.codex/commands/README.md` | Public command catalog pattern without private command bodies. |

## System Responsibilities

The system layer should answer six questions for every non-trivial task:

1. What context should the agent load before acting?
2. Which capability should the agent use first?
3. What must be delivered before memory work begins?
4. What evidence is required before a claim is trusted?
5. What route should be strengthened, weakened, or suppressed?
6. What should never be published or saved?

## Adoption Order

1. Start with `AGENTS.example.md`.
2. Add `_CLAUDE.md`, `index.md`, `Home.md`, and `CRITICAL_FACTS.md` to your own vault.
3. Use `capture-routing.md` manually until the save boundary feels reliable.
4. Add `memory-graph.md` once you can identify repeated successful and failed routes.
5. Add `weekly-consolidation.md` when append-only captures start piling up.

## Safety Boundary

Keep this folder public-safe. Do not add credentials, raw transcripts, customer names, production document numbers, private screenshots, company-specific procedures, or real private vault exports.

