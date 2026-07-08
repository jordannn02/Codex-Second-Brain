# Capture Routing

Capture routing decides what should be preserved after the user-visible result is delivered.

## Save

Save when the task produced something reusable:

| Signal | Examples |
|---|---|
| Decision | Chosen architecture, publishing boundary, project scope. |
| Evidence chain | Source file, query, log, screenshot, verification result. |
| Reusable mapping | Business term to field, command to workflow, error to fix. |
| Workflow lesson | A tool path worked, failed, or should be avoided next time. |
| Deliverable | Report, generated file, handoff, checklist, spec. |

## Do Not Save

Do not save:

- trivial chat;
- credentials or tokens;
- raw private screenshots;
- financial or personal records without explicit permission;
- unverified guesses;
- external proprietary prompt text;
- data the user explicitly marked as not for saving.

## Delivery-First Rule

Never make the user wait for memory capture before they see the result.

Use this sequence:

```text
1. Deliver the answer or artifact.
2. Decide whether capture is warranted.
3. Write the smallest durable note.
4. Leave broad index cleanup to weekly consolidation.
```

## Minimal Write Rule

For routine capture, write at most one durable target immediately. Prefer:

- one project note update;
- one dated knowledge note;
- one dev log;
- one append-only capture note.

Do not update many indexes, backlinks, daily notes, and logs in the same routine capture unless the user explicitly asked for vault maintenance.

