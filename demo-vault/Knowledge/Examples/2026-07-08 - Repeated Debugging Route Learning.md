---
date: 2026-07-08
type: knowledge
tags:
  - demo
  - debugging
  - memory-graph
  - route-learning
ai-first: true
source: "Synthetic public demo fixture."
confidence: example
aliases:
  - 重複除錯路徑學習
  - 雜訊搜尋後的圖譜優先除錯
---

# Repeated Debugging Route Learning

## For future Claude

Use this note to demonstrate how the system learns from a failed debugging route. The important behavior is that the noisy route is weakened while the verified corrected route is reinforced.

## Scenario

The user asks the agent to diagnose why a feature fails after a recent change.

## First Attempt

The agent starts with broad text search:

```text
search whole repo -> too many matches -> no clear root cause
```

Outcome: slow and noisy.

## Corrected Route

The agent switches to a graph-first path:

```text
repo map -> call trace -> source snippet -> targeted test -> verified fix
```

Outcome: faster and easier to verify.

## Memory Graph Update

```json
{
  "from": "debugging task with many text matches",
  "avoid_if": "broad search returns noisy unrelated hits",
  "preferred_tool_for": "code graph and call trace first",
  "evidence": ["targeted test passed", "source snippet reviewed"],
  "action": "Start with graph navigation before broad text search."
}
```

## Reusable Lesson

When broad search creates noise, weaken that route and reinforce graph-first debugging for similar tasks.
