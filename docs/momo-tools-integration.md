# momo-tools Integration

`momo-tools` and Codex Second Brain OS solve adjacent parts of an agent operating loop.

```text
user task
  -> momo-tools route / gate / verify
  -> agent executes bounded task
  -> user-visible delivery
  -> Codex Second Brain captures durable signal
  -> memory graph strengthens or weakens route
  -> future routing starts smarter
```

## Responsibility Split

| Layer | Answers | Output |
|---|---|---|
| `momo-tools` | Which capability should handle this task? What risk gates apply? Is this capability verified-working? | Route result, gate decision, verification evidence. |
| Codex Second Brain OS | What happened this time? Should this route be reinforced, weakened, or suppressed next time? | Capture event, memory edge, consolidation report. |

## Synthetic Fixture

This repository includes a public-safe route result:

```text
demo-vault/fixtures/momo-route-result.json
```

It demonstrates how a capability router result can become:

1. a capture event in `demo-vault/fixtures/capture-events.jsonl`;
2. a candidate memory edge in `demo-vault/fixtures/memory-graph.jsonl`;
3. a future `route-suggest` result.

## Example

```bash
python3 -m codex_second_brain.cli route-suggest \
  demo-vault \
  "publish a safe documentation change to GitHub"
```

The second brain does not replace the router. It gives the router historical context about what worked, what failed, and what proof was required.

## Safety Boundary

Do not send private route results directly into a public memory graph. Redact or summarize first:

- capability name, not private connector details;
- risk category, not secrets;
- verification summary, not raw private logs;
- public-safe evidence path, not private screenshots or transcripts.
