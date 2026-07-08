# Memory Graph

The memory graph is a lightweight routing layer for agent work.

It records what path was useful, what failed, and what evidence supports the route.

## Edge Shape

```json
{
  "id": "edge_delivery_first",
  "from": "normal user task",
  "to": "deliver first then capture",
  "relation": "workflow_shortcut",
  "weight": 0.9,
  "confidence": "verified-by-use",
  "evidence": ["AGENTS.example.md", "capture-routing.md"],
  "action": "Finish visible work before memory writes.",
  "interruption_policy": "Interrupt if capture would expose private data."
}
```

## Useful Relations

| Relation | Meaning |
|---|---|
| `preferred_tool_for` | Use this tool first for this task type. |
| `workflow_shortcut` | A proven sequence for a recurring workflow. |
| `evidence_chain` | Proof route needed before claiming a result. |
| `verified_by` | Verification command, test, or artifact. |
| `avoid_if` | Avoid this path under a specific failure signature. |
| `suppress` | Demote a route without deleting history. |

## Practical Loop

1. Run a preflight for the task summary.
2. Use hot/direct positive edges as routing guidance.
3. Treat avoid/suppress edges as warnings.
4. After work, record whether the route succeeded.
5. If a route was wrong, self-correct instead of repeating it.

## Boundary

The graph is advisory. It does not authorize destructive changes, production updates, or skipping fresh verification.

