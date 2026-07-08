# Weekly Consolidation

Weekly consolidation is the automatic maintenance loop that keeps the second brain usable without turning every task into cleanup work.

## What It Does

- refresh navigation indexes;
- surface stale rules;
- detect orphan notes;
- review low-confidence graph edges;
- decay unused routes;
- promote repeated captures into reusable rules;
- report cleanup candidates before destructive action;
- preserve evidence-bearing notes.

## Automatic Trigger Model

Consolidation can be triggered by:

- a scheduled weekly automation;
- an explicit command;
- a post-delivery maintenance step;
- a health-check report;
- repeated graph failures that suggest a route needs review.

## Safe Actions

Safe weekly actions:

- append missing backlinks;
- update index descriptions;
- summarize recent logs;
- flag stale tasks;
- identify duplicate candidates;
- lower weights on unused graph edges;
- create a review report for risky cleanup.

## Actions That Need Explicit Permission

Ask before:

- deleting notes;
- archiving evidence;
- merging notes;
- rewriting dense historical logs;
- publishing or exporting private content;
- modifying production systems.

## Report Format

```text
configured: what automation or rule exists
executed: what actually ran
verified-working: what was checked and passed
pending: what still needs review
```

This distinction prevents confusing "set up" with "proven working".

