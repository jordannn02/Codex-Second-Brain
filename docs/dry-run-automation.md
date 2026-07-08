# Dry-Run-First Automation

The public reference package treats automation as report-first. This is intentional: second-brain systems can touch private notes, long-term memory, and agent behavior, so invisible cleanup is risky.

## Principle

```text
observe -> report -> review -> write only when approved
```

The system may automatically detect candidates, but it should not automatically delete, archive, merge, publish, or rewrite evidence-bearing notes.

## CLI Behavior

### Capture

By default, capture prints the event and does not write:

```bash
python3 -m codex_second_brain.cli capture \
  --vault demo-vault \
  --type route-worked \
  --summary "Debugging route succeeded after graph-first tracing" \
  --evidence "demo-vault/fixtures/memory-graph.jsonl"
```

Add `--write` only when you want to append to `captures.jsonl`.

### Consolidation

Consolidation reports what it sees:

```bash
python3 -m codex_second_brain.cli consolidate demo-vault --dry-run
```

The report may include:

- missing startup files;
- orphan candidates;
- low-confidence memory edges;
- permission-required actions.

## Permission Required

Ask before:

- deleting notes;
- archiving evidence;
- merging notes;
- rewriting dense historical logs;
- publishing or exporting private content;
- modifying production systems.

## Why This Matters

Memory systems are powerful because they shape future behavior. A bad automatic cleanup can remove proof, hide contradictions, or teach agents the wrong route. Dry-run-first keeps memory evolution inspectable.
