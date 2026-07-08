# Memory Graph

The memory graph is the adaptive learning layer of Codex Second Brain OS. It turns workflow experience into inspectable routing edges.

A successful path becomes easier to reuse. A failed path becomes weaker, guarded, or suppressed. A corrected path becomes the new preferred route.

## Edge Shape

Memory edges are stored as JSONL and can be validated against `schemas/memory-edge.schema.json`.

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
  "last_used": "2026-07-08T12:00:00Z",
  "evidence": [
    "Knowledge/Examples/2026-07-08 - Repeated Debugging Route Learning.md"
  ],
  "action": "Start graph navigation and call tracing when broad search returns noisy unrelated hits.",
  "interruption_policy": "Do not treat route memory as proof; verify source snippets and targeted tests."
}
```

## Relation Types

| Relation | Meaning |
|---|---|
| `preferred_tool_for` | Use this route first for a task type. |
| `workflow_shortcut` | A proven sequence for a recurring workflow. |
| `evidence_chain` | A proof path required before a claim is trusted. |
| `verified_by` | A test, command, file, or artifact confirms a claim. |
| `avoid_if` | Avoid a route under a specific failure signature. |
| `suppress` | Demote a route without deleting historical evidence. |
| `supersedes` | Mark one conclusion or route as replacing an older one. |

## Reinforcement

When a route succeeds with verification evidence:

- increase `weight`;
- increase `success_count`;
- refresh `last_used`;
- mark it `hot` if it repeatedly helps;
- keep the exact evidence path.

This makes future preflight more likely to choose the route.

## Weakening and Suppression

When a route fails:

- increase `fail_count`;
- attach the failure signature;
- reduce confidence or weight;
- create `avoid_if` when the failure is conditional;
- create `suppress` when the route should be demoted broadly.

The system does not erase history. It preserves evidence while making bad paths less attractive.

## Adaptive Correction Loop

```text
preflight -> choose route -> execute -> verify -> record outcome
  -> if wrong, self-correct
  -> strengthen corrected route
  -> weaken failed route
```

## CLI Example

```bash
python3 -m codex_second_brain.cli route-suggest \
  demo-vault \
  "debugging noisy search source trace"
```

## Boundary

The memory graph is advisory. It does not authorize destructive changes, production updates, credential access, or skipping fresh verification when the task requires proof.
