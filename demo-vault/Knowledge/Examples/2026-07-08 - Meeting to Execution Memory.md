---
date: 2026-07-08
type: knowledge
tags:
  - demo
  - meeting
  - execution-memory
  - consolidation
ai-first: true
source: "Synthetic public demo fixture."
confidence: example
---

# Meeting to Execution Memory

## For future Claude

Use this note to demonstrate automatic capture after a meeting. The agent delivers the meeting summary first, then captures durable execution memory.

## Scenario

A meeting produces:

- a decision;
- an owner;
- a due date;
- a risk;
- a repeated theme from previous meetings.

## Delivery First

The agent first returns the usable meeting summary:

```text
decision -> owner -> due date -> risk -> next verification step
```

## Post-Delivery Capture

After delivery, the system saves durable signals:

- decision and rationale;
- owner and next action;
- repeated theme;
- contradiction with prior notes, if any;
- consolidation candidate.

## Weekly Consolidation

Repeated meeting themes can become reusable rules. Contradictions between old decisions and new conclusions are surfaced for review instead of silently overwritten.

## Reusable Lesson

Meeting memory is not just a transcript. It is a bridge from discussion to execution.

