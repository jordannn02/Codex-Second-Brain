# Roadmap

This roadmap keeps the project honest about what is implemented now versus what remains design-level.

## v0.2 - Public Reference Package

Status: implemented in the local reference package.

- Add MIT license and security policy.
- Add machine-readable schemas.
- Add minimal CLI:
- `init`
- `validate`
- `capture`
- `consolidate --dry-run`
- `route-suggest`
- Treat `demo-vault/` as the golden fixture.
- Add tests and GitHub Actions CI.
- Add synthetic `momo-tools` integration fixture.

## v0.3 - Real Consolidation Runner

Goal: make consolidation useful while staying dry-run-first.
Status: partially implemented locally.

- Generate machine-readable consolidation report with `proposed_changes[]`.
- Detect duplicate candidates.
- Detect stale or low-confidence memory graph edges.
- Suggest index updates.
- Suggest capture promotion into memory graph edges.
- Keep all risky actions approval-gated.

## v0.4 - Memory Graph Operations

Goal: make route memory updateable with tools.
Status: implemented locally.

- Add `record-outcome`.
- Add `decay`.
- Add `self-correct`.
- Add edge explainability.
- Add schema-backed validation with built-in fallback.

## v0.5 - Router Feedback Loop

Goal: close the loop with external capability routers.
Status: first local loop implemented.

- Ingest `momo-tools` route results.
- Convert verified outcomes into capture events.
- Promote repeated successes into `preferred_tool_for` edges.
- Promote repeated failures into `avoid_if` or `suppress` edges.

## Non-Goals

- This project will not publish private vault exports.
- This project will not perform destructive cleanup without explicit approval.
- This project will not treat memory as proof.
- This project will not replace source, test, runtime, or data verification.
