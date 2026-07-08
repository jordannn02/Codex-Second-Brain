# Schemas

The `schemas/` folder makes the project more than prose. It defines the durable data shapes that tools, CI jobs, and future agents can validate.

## `memory-edge.schema.json`

A memory edge records a reusable route.

Common uses:

- strengthen a route that succeeded;
- weaken a route with repeated failure signatures;
- preserve an evidence chain required before a conclusion is trusted;
- suppress a route without deleting historical evidence.

Minimal example:

```json
{
  "id": "edge_debugging_graph_first_after_noisy_search",
  "from": "debugging task with many noisy text matches",
  "to": "repo map -> call trace -> source snippet -> targeted test",
  "relation": "preferred_tool_for",
  "weight": 0.86,
  "confidence": "verified-by-use",
  "decay_state": "hot",
  "success_count": 3,
  "fail_count": 1,
  "evidence": ["Knowledge/Examples/2026-07-08 - Repeated Debugging Route Learning.md"],
  "action": "Start graph navigation and call tracing when broad search returns noisy unrelated hits."
}
```

## `capture-event.schema.json`

A capture event is a post-delivery memory candidate. It should be small and reviewable.

Common uses:

- route worked;
- route failed;
- decision made;
- proof chain assembled;
- reusable mapping discovered;
- deliverable created;
- contradiction detected.

## `vault-index.schema.json`

A vault index is a machine-readable navigation map. It should stay small enough to load before broad search.

The Markdown `index.md` remains human-friendly. A JSON index can be generated later for faster tooling, CI validation, or external agent handoff.

## Validation Strategy

The reference CLI currently performs lightweight validation without external dependencies:

```bash
python3 -m codex_second_brain.cli validate demo-vault
```

Full JSON Schema validation can be added in downstream projects using `jsonschema`, IDE schema registration, or a pre-commit hook.
