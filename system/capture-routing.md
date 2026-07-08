# Capture Routing

Capture routing decides what becomes durable memory after the user-visible task is complete.

The goal is not to save everything. The goal is to save the smallest signal that will make future work faster, safer, or more accurate.

## Automatic Capture Triggers

Save when the task produced reusable material:

| Trigger | Save |
|---|---|
| A route worked | Task context, selected capability, verification evidence, output path. |
| A route failed | Failed path, error signature, likely cause, corrected route if known. |
| A decision was made | Decision, rationale, scope, exception, source. |
| A proof chain was assembled | Source file, query, log, screenshot boundary, runtime check, result. |
| A reusable mapping appeared | Business term to field, command to workflow, error to fix. |
| A deliverable was created | Report, generated file, handoff, checklist, spec, verification note. |

## Do Not Capture

Do not save:

- trivial chat;
- credentials, tokens, keys, or secrets;
- raw private screenshots;
- financial or personal records without explicit permission;
- unverified guesses as fact;
- external proprietary prompt text;
- anything the user explicitly marked as not for saving.

## Delivery-First Rule

Never make the user wait for memory capture before they see the result.

Use this sequence:

```text
1. Deliver the answer or artifact.
2. Decide whether capture is warranted.
3. Write the smallest durable note or graph edge.
4. Leave broad cleanup to scheduled consolidation.
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

