# Agent Operating Defaults

Use this as a public-safe starting point for a Codex + Obsidian second brain.

## Startup Context

For non-trivial tasks where vault context may matter, read these files first:

1. `_CLAUDE.md` - vault-specific operating rules.
2. `index.md` - navigation map.
3. `Home.md` - current dashboard.
4. `CRITICAL_FACTS.md` - tiny always-load context.

Report startup context clearly when it matters:

```text
Startup context: loaded _CLAUDE/index/Home/CRITICAL_FACTS.
```

## Capability Router

Before acting, classify the task:

- quick answer;
- code or repo work;
- document / spreadsheet / slide / PDF / image work;
- database / source tracing / system investigation;
- browser or app connector work;
- data analysis / dashboard / report;
- current or latest information;
- automation or recurring workflow.

Then choose the narrowest useful capability. Do not call tools only because they exist.

## Delivery First

For normal user work:

1. Complete the visible user task first.
2. Give the answer, file, query result, artifact, or handoff.
3. Only after that, run capture, memory graph feedback, rule promotion, or consolidation.

## Evidence Boundary

Keep proof layers separate:

- memory or notes: context, not proof;
- documentation: intended behavior;
- source code: implemented behavior;
- database/query: current data state;
- runtime/manual test: observed behavior;
- write authority: separate permission boundary.

## Capture Rule

Save only material that reduces future lookup or prevents repeated mistakes:

- decisions;
- exact commands or query shapes;
- field / setting / source-path mappings;
- error strings and root causes;
- verification results;
- reusable workflow lessons.

Do not save trivial chat, secrets, raw credentials, highly private data, or unverified speculation as fact.

## Public Repo Boundary

Public repos should contain method, fixtures, and redacted examples.

Private repos or local vaults should contain real notes, clients, transcripts, financial data, production IDs, and internal company details.

