---
description: obsidian-architect — portable task instructions with explicit write authorization
category: meta
triggers_en: ["document this codebase", "architect this project", "map this code into my vault", "generate architecture notes", "refresh architecture docs"]
---

# /obsidian-architect

Map the specified repository through files and targeted source inspection. Explain entry points, ownership boundaries, data flow, external dependencies, tests and design decisions with file/line anchors. Do not include credentials or proprietary source excerpts in an external artifact. Default to a report in chat. A requested bounded set of architecture notes is explicit multi-file work: declare those targets under EXPLICIT_MAINTENANCE, preserve user sections, and do not add extra indexes or backlinks. No code-scanning helper is required.

## Authorization and execution boundary

Read `_CLAUDE.md` if present and the smallest relevant index/source. State which startup context was read. These are portable agent instructions, not CLI subcommands or a separately installed skill. Use available read-only tools or local Python; never invent a connector, credential, completed operation, or missing helper.

A research, search, review, correction, useful result, or completed task does not authorize saving. A command whose explicit purpose is creating/updating a note authorizes that requested target only. Ordinary saves use at most one durable target. Do not add Daily, board, index, log, backlink, stub, PINNED, graph feedback, or retrospective writes as follow-ups. A reusable-rule request authorizes one target containing Trigger / Rule / Scope / Evidence / Exception; it does not authorize changes to global rules or skills.

For an authorized write, enumerate exact relative targets and run:
```bash
python3 .codex/scripts/capture_gate.py --path . --mode EXPLICIT_COMMAND --target "<relative-note.md>" --dry-run --json
```
`EXPLICIT_COMMAND` permits at most one target. Explicitly requested bounded multi-file maintenance uses `EXPLICIT_MAINTENANCE` (at most five targets per manifest); `WEEKLY_CONSOLIDATION` is only for an existing authorized scheduled scope. `AUTO_CAPTURE` is disabled. A gate result is not authorization. Write only `manifest.proposed_changes`, execute its exact required post-write validation command, then read back the same targets. Preserve existing changes and evidence; do not rewrite/reformat unrelated history. Missing gate or required validation is a blocker for a write, not a reason to bypass it.

Read `.codex/references/ai-first-rules.md` and `.codex/references/write-rules.md` before note writes. New notes require `type`, `date`, `tags`, `ai-first: true`, `## For future Claude`, relevant wikilinks, dated sources and confidence where needed. Report unknown values rather than inventing them. Deliver the usable result before an attached save; if saving is the primary task, perform it directly. Retrospective analysis and saving its output require their respective authorization. Never save secrets. Sensitive, destructive, external-upload and production actions require corresponding authorization. No automatic external messages, uploads, scheduling, deletion, archive or merge.
