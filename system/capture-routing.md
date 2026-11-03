# Capture Routing

Capture routing decides what becomes durable memory after the user-visible task is complete.

The goal is not to save everything. The goal is to save the smallest signal that will make future work faster, safer, or more accurate.

## Explicit Authorization First

Ordinary conversations do not trigger automatic capture. Save only when the user explicitly requests it or an existing authorized maintenance workflow covers it. A correction, failed attempt, useful insight, or completed deliverable is not permission to save. Do not run a retrospective or promote rules automatically.

After authorization, choose the smallest useful material:

| Trigger | Save |
|---|---|
| A route worked | Task context, selected capability, verification evidence, output path. |
| A route failed | Failed path, error signature, likely cause, corrected route if known. |
| A decision was made | Decision, rationale, scope, exception, source. |
| A proof chain was assembled | Source file, query, log, screenshot boundary, runtime check, result. |
| A reusable mapping appeared | Business term to field, command to workflow, error to fix. |
| A deliverable was created | Report, generated file, handoff, checklist, spec, verification note. |
| A contradiction appeared | Old conclusion, new evidence, current trusted conclusion, open question if unresolved. |

## Do Not Capture

Do not save:

- trivial chat;
- credentials, tokens, keys, or secrets;
- raw private screenshots;
- financial or personal records without explicit permission;
- unverified guesses;
- external proprietary prompt text;
- anything the user explicitly marked as not for saving.

## Delivery-First Rule

Never make the user wait for memory capture before they see the result.

Use this sequence:

```text
1. Deliver answer or artifact.
2. Check explicit save authorization or the existing maintenance scope; otherwise stop.
3. Plan the smallest authorized target and inspect the dry-run result.
4. Write only the authorized target, validate it, and read it back.
5. Leave broad cleanup to scheduled consolidation.
```

## Minimal Write Rule

For routine capture, write at most one durable target immediately.

Prefer:

- one project note update;
- one dated knowledge note;
- one dev log;
- one graph edge;
- one append-only capture note.

Do not update many indexes, backlinks, daily notes, and logs in the same routine capture unless the task is explicitly vault maintenance.

## CLI Example

```bash
python3 -m codex_second_brain.cli capture \
  --vault demo-vault \
  --type route-worked \
  --summary "Debugging route succeeded after graph-first tracing" \
  --evidence "demo-vault/fixtures/memory-graph.jsonl"
```

This command prints the event without writing. Add `--write` only when persistence is authorized. A dry-run or `safe_to_apply` result does not grant authorization. A request to save a note does not also authorize graph updates.

Reusable-rule requests require `Trigger / Rule / Scope / Evidence / Exception` in one approved target. Do not change global agent instructions or skills unless requested. See [the usage guide](../docs/usage-zh-TW.md) for the personal-vault Capture Gate boundary.
