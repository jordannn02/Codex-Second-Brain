# Memory Graph

The memory graph is the adaptive learning layer of Codex Second Brain OS.

It turns workflow experience into inspectable routing edges. A successful path becomes easier to reuse. A failed path becomes weaker, guarded, or suppressed. A corrected path becomes the new preferred route.

## Edge Shape

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
  "evidence": [
    "demo-vault/Knowledge/Examples/2026-07-08 - Repeated Debugging Route Learning.md"
  ],
  "action": "Start with graph navigation and call tracing when broad search returns noisy unrelated hits.",
  "interruption_policy": "Do not treat memory as proof; verify with source snippets and targeted tests."
}
```

## Relation Types

| Relation | Meaning |
|---|---|
| `preferred_tool_for` | Use this tool or route first for a task type. |
| `workflow_shortcut` | A proven sequence for a recurring workflow. |
| `evidence_chain` | A proof path required before a claim is trusted. |
| `verified_by` | A test, command, file, or artifact that confirms the claim. |
| `avoid_if` | Avoid this route under a specific failure signature. |
| `suppress` | Demote a route without deleting historical evidence. |

## Autonomous Reinforcement

When a route succeeds and has verification evidence:

- increase `weight`;
- increase `success_count`;
- refresh `last_used`;
- mark it `hot` if it repeatedly helps;
- keep the exact evidence path.

This makes future preflight more likely to choose the route.

## Weakening and Suppression

When a route fails:

- increase `fail_count`;
- attach the error signature;
- reduce confidence or weight;
- create `avoid_if` when the failure is conditional;
- create `suppress` when the route should be demoted broadly.

The system does not forget. It keeps the history while making bad paths less attractive.

## Adaptive Correction Loop

```text
preflight -> choose route -> execute -> verify -> record outcome
                                      -> if wrong, self-correct
                                      -> strengthen corrected route
                                      -> weaken failed route
```

This allows the system to learn from both success and failure without relying on hidden model memory.

## Boundary

The memory graph is advisory. It does not authorize destructive changes, production updates, credential access, or skipping fresh verification when the task requires proof.

