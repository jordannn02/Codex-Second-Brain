# Roadmap

This roadmap keeps the project honest about what is implemented now and what remains design-level.

## v0.2 - Public Reference Package

Status: in progress.

- Add MIT license and security policy.
- Add machine-readable schemas.
- Add minimal CLI:
  - `init`
  - `validate`
  - `capture`
  - `consolidate --dry-run`
  - `route-suggest`
- Treat `demo-vault/` as a golden fixture.
- Add tests and GitHub Actions CI.
- Add synthetic `momo-tools` integration fixture.

## v0.3 - Real Consolidation Runner

Goal: make consolidation useful while staying dry-run-first.

- Generate a machine-readable consolidation report.
- Detect duplicate candidates.
- Detect stale memory graph edges.
- Suggest index updates.
- Suggest capture promotion into memory graph edges.
- Keep all risky actions approval-gated.

## v0.4 - Memory Graph Operations

Goal: make route memory updateable by tools.

- Add `record-outcome`.
- Add `decay`.
- Add `self-correct`.
- Add edge explainability.
- Add JSON Schema validation in CI.

## v0.5 - Router Feedback Loop

Goal: close the loop with external capability routers.

- Ingest `momo-tools` route results.
- Convert verified outcomes into capture events.
- Promote repeated successes into `preferred_tool_for` edges.
- Promote repeated failures into `avoid_if` or `suppress` edges.

## Non-Goals

- This project will not publish private vault exports.
- This project will not perform destructive cleanup without explicit approval.
- This project will not treat memory as proof.
- This project will not replace source, test, runtime, or data verification.
