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
---

# Tool Overload Auto Router

## For future Claude

Use this note to demonstrate capability-aware routing. The user should not need to remember which skill, plugin, connector, or local tool fits each task.

## Scenario

The user has many tools available:

- document conversion;
- GitHub;
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
| Repo work | Use GitHub or local repo tools. |
| UI verification | Use browser automation. |
| Data question | Use SQL or structured data tools. |
| Repeated workflow | Check the memory graph first. |
| Meeting follow-up | Summarize, extract decisions, create execution memory. |

## Memory Graph Update

Successful routing decisions can strengthen `preferred_tool_for` edges. Repeated tool mistakes can create `avoid_if` edges.

## Reusable Lesson

The agent should route by task shape, not by the user's ability to name the right tool.

