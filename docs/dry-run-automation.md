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

The report also returns `proposed_changes[]`. Each item includes:

- `type`: the proposed operation, such as `review_orphan_candidate`;
- `target`: the file or edge affected;
- `reason`: why it was proposed;
- `requires_permission`: whether human approval is required before writing;
- `safe_to_apply`: whether the CLI considers the operation mechanically safe.

### Memory Graph Operations

Memory updates are dry-run-first too. These commands print the proposed edge state unless `--write` is set:

```bash
python3 -m codex_second_brain.cli record-outcome demo-vault --edge-id edge_tool_overload_use_capability_router --outcome success
python3 -m codex_second_brain.cli self-correct demo-vault --failed-edge-id old --corrected-edge-id new --from "old route" --to "new route" --action "Use verified route."
python3 -m codex_second_brain.cli decay demo-vault --days-unused 30 --amount 0.1
python3 -m codex_second_brain.cli ingest-momo-route demo-vault demo-vault/fixtures/momo-route-result.json
```

`explain-edge` is read-only and can be used before trusting a route suggestion:

```bash
python3 -m codex_second_brain.cli explain-edge demo-vault edge_debugging_graph_first_after_noisy_search
```

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
