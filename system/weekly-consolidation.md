# Weekly Consolidation

Weekly consolidation is the maintenance loop that keeps a second brain usable without turning every task into cleanup work.

The public reference implementation is dry-run-first. It reports candidates before any write, and it never performs destructive cleanup.

## What It Does

- refresh navigation indexes;
- surface stale rules;
- detect orphan notes;
- review low-confidence graph edges;
- decay unused routes;
- promote repeated captures into reusable rules;
- report cleanup candidates before destructive action;
- preserve evidence-bearing notes.

## Trigger Model

Consolidation runs only on an explicit request or an existing authorized scheduled workflow, within its saved scope. Health reports and repeated failures may be review candidates; they do not authorize maintenance, persistence, or rule promotion. A post-delivery step is not an automatic trigger.

## Safe Dry-Run Actions

Safe dry-run actions:

- count Markdown files;
- find missing startup files;
- identify orphan candidates;
- list low-confidence memory edges;
- flag stale tasks;
- identify duplicate candidates;
- report permission-required actions.

## Actions That Need Explicit Permission

Ask before:

- deleting notes;
- archiving evidence;
- merging notes;
- rewriting dense historical logs;
- publishing or exporting private content;
- modifying production systems.

## CLI Example

```bash
python3 -m codex_second_brain.cli consolidate demo-vault --dry-run
```

## Report Format

```text
configured: automation rule exists
executed: actually ran
verified-working: what was checked and passed
pending: what still needs review
```

This distinction prevents confusing "set up" with "proven working".
