---
date: 2026-07-08
type: knowledge
tags:
  - demo
  - capability-routing
  - tools
  - auto-router
ai-first: true
source: "Synthetic public demo fixture."
confidence: example
aliases:
  - 工具過載自動路由
---

# Tool Overload Auto Router

## For future Claude

Use this note to demonstrate capability-aware routing. The user should not need to remember which skill, plugin, connector, or local tool fits a task.

## Scenario

The user has many tools available:

- document conversion;
- GitHub workflows;
- browser automation;
- SQL;
- dashboards;
- meeting summaries;
- vault search;
- memory graph routing.

## Routing Behavior

The agent classifies the task first:

| Task type | Preferred route |
|---|---|
| File or PDF analysis | Convert to Markdown, then inspect. |
| Repo work | Use GitHub and local repo tools. |
| UI verification | Use browser automation. |
| Data question | Use structured SQL or data tools. |
| Repeated workflow | Check memory graph first. |
| Meeting follow-up | Summarize, extract decisions, then capture execution memory. |

## Memory Graph Update

Successful routing decisions strengthen `preferred_tool_for` edges. Repeated tool mistakes create `avoid_if` edges.

## Reusable Lesson

The agent should route by task shape, not by the user's ability to name the right tool.
